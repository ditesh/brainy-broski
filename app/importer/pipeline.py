"""PDF -> papers, questions and problems. Runs in a background task with its own session."""
import logging
import re
from pathlib import Path

import pymupdf as fitz
from sqlalchemy.orm import Session

from app.ai.client import AIClient
from app.ai.prompts import ANALYSE_SYSTEM, STRUCTURE_SYSTEM
from app.ai.schemas import PageBoxes, PdfStructure, QuestionAnalysis, Section
from app.answers import normalise
from app.config import Settings
from app.importer.dedupe import link_duplicates
from app.importer.solutions import answers_from_solutions
from app.models import FollowupResponse, ImportStatus, Paper, PaperQuestion, Problem, Response, SourcePdf
from app.pdf.render import (CropBox, crop_box, crop_questions, extract_figures, find_anchors, has_text_layer,
                            render_pages)
from app.techniques import TECHNIQUES

log = logging.getLogger(__name__)

PAGE_BOXES_SYSTEM = """You are given one page of a maths olympiad paper. Find every numbered question \
on it. For each, return its number and a bounding box that covers the whole question including any \
diagram and answer choices, as fractions of the page width and height (0 = left/top, 1 = right/bottom). \
Exclude page headers, footers and part headings."""


def _plain(e: Exception) -> str:
    """AIErrors already carry a friendly sentence; anything else gets a generic one (details are in the log)."""
    from app.ai.client import AIError
    return str(e) if isinstance(e, AIError) else "Something unexpected went wrong while reading the paper. Press Retry."


def _tag_list() -> str:
    return "\n".join(f"- {tag}: {name}" for tag, name, _ in TECHNIQUES)


def detect_structure(source_pdf_id: int, db: Session, ai: AIClient, settings: Settings) -> None:
    src = db.get(SourcePdf, source_pdf_id)
    src.status, src.error = ImportStatus.running, None
    db.commit()
    try:
        pages = render_pages(Path(src.path), settings.data_dir / "pages" / str(src.id), dpi=72)
        result = ai.structured(PdfStructure, STRUCTURE_SYSTEM, pages,
                               f"This PDF has {len(pages)} pages. Describe its structure.", "low")
        src.structure = result.model_dump(mode="json")
        from app.importer.year import UNKNOWN_YEAR
        if src.year == UNKNOWN_YEAR and result.year and 1990 <= result.year <= 2100:
            src.year = result.year
        src.status = ImportStatus.needs_review
    except Exception as e:  # never leave the import stuck in "running"
        log.exception("structure detection failed")
        db.rollback()
        src = db.get(SourcePdf, source_pdf_id)
        src.status, src.error = ImportStatus.failed, _plain(e)
    db.commit()


def _points_for(section: Section, n: int) -> tuple[str, int, int]:
    """(part name, points for a right answer, points lost for a wrong one)."""
    for part in section.parts:
        if part.first_question <= n <= part.last_question:
            return part.name, part.points, part.wrong_points
    return "", 1, 0


def _answers_for(structure: PdfStructure, section: Section) -> dict[int, str]:
    same = lambda a, b: a.strip().casefold() == b.strip().casefold()
    keys = [k for k in structure.answer_keys if same(k.category, section.category)]
    if section.year is not None and any(k.year == section.year for k in keys):
        keys = [k for k in keys if k.year == section.year]
    return {e.question: e.answer.strip() for e in keys[0].answers} if keys else {}


def _english(structure: PdfStructure) -> list[Section]:
    return [s for s in structure.sections if s.language == "en"]


def _multi_year(structure: PdfStructure) -> bool:
    return len({s.year for s in _english(structure) if s.year}) > 1


def section_key(section: Section, multi_year: bool) -> str:
    """The name a parent ticks to import this section: the level, plus the year if the PDF has several."""
    return f"{section.category} · {section.year}" if multi_year and section.year else section.category


def choice_keys(src: SourcePdf) -> list[str]:
    if not src.structure:
        return []
    st = PdfStructure.model_validate(src.structure)
    multi = _multi_year(st)
    keys: list[str] = []
    for s in _english(st):
        k = section_key(s, multi)
        if k not in keys:
            keys.append(k)
    return keys


def crop_dir(settings: Settings, paper: Paper) -> Path:
    # the level name comes from the PDF via Claude: keep it to a safe folder name
    name = re.sub(r"[^A-Za-z0-9]+", "-", paper.category).strip("-") or "paper"
    if paper.year:
        name += f"-{paper.year}"
    return settings.data_dir / "crops" / str(paper.source_pdf_id) / name


def _crops_via_ai(pdf: Path, section: Section, out_dir: Path, ai: AIClient, settings: Settings,
                  src_id: int) -> dict[int, list[CropBox]]:
    page_imgs = render_pages(pdf, settings.data_dir / "pages" / str(src_id))
    crops: dict[int, list[CropBox]] = {}
    with fitz.open(pdf) as doc:
        for pno in range(section.first_page, section.last_page + 1):
            w, h = doc[pno - 1].rect.width, doc[pno - 1].rect.height
            boxes = ai.structured(PageBoxes, PAGE_BOXES_SYSTEM, [page_imgs[pno - 1]],
                                  f"Page {pno}. Return the question boxes.", "low")
            for b in boxes.boxes:
                rect = (b.x0 * w, b.y0 * h, b.x1 * w, b.y1 * h)
                path = out_dir / f"q{b.number:03}-{len(crops.get(b.number, []))}.png"
                crop_box(pdf, pno, rect, path)
                crops.setdefault(b.number, []).append(CropBox(pno, *rect, path))
    return crops


def _has_history(db: Session, paper: Paper) -> bool:
    pq_ids = [q.id for q in paper.questions]
    problem_ids = [q.problem_id for q in paper.questions]
    return bool(db.query(Response).filter(Response.paper_question_id.in_(pq_ids)).count()
                or db.query(FollowupResponse).filter(FollowupResponse.problem_id.in_(problem_ids)).count())


def _clear_unpublished(db: Session, src: SourcePdf, categories: list[str]) -> None:
    """Remove earlier unpublished imports of these sections, unless the child has used them."""
    for paper in db.query(Paper).filter(Paper.source_pdf_id == src.id).all():
        if paper.choice_key in categories and not paper.published and not _has_history(db, paper):
            problem_ids = {q.problem_id for q in paper.questions}
            for q in list(paper.questions):
                db.delete(q)
            db.delete(paper)
            db.flush()
            for pid in problem_ids:
                if (not db.query(PaperQuestion).filter(PaperQuestion.problem_id == pid).count()
                        and not db.query(FollowupResponse).filter(FollowupResponse.problem_id == pid).count()):
                    db.delete(db.get(Problem, pid))
    db.flush()


def run_import(source_pdf_id: int, categories: list[str], db: Session, ai: AIClient, settings: Settings) -> None:
    src = db.get(SourcePdf, source_pdf_id)
    structure = PdfStructure.model_validate(src.structure)
    pdf = Path(src.path)
    src.status, src.error = ImportStatus.running, None
    db.commit()
    try:
        _clear_unpublished(db, src, categories)
        db.commit()
        text_layer = has_text_layer(pdf)
        multi = _multi_year(structure)
        for section in _english(structure):
            if section_key(section, multi) not in categories:
                continue
            paper = Paper(source_pdf_id=src.id, category=section.category, language="en",
                          year=section.year if multi else None,
                          duration_min=src.duration_min, published=False)
            db.add(paper)
            db.commit()  # don't hold the SQLite write lock during the slow AI calls below
            out_dir = crop_dir(settings, paper)
            if text_layer:
                anchors = find_anchors(pdf, list(range(section.first_page, section.last_page + 1)))
                crops = crop_questions(pdf, anchors, out_dir)
            else:
                crops = _crops_via_ai(pdf, section, out_dir, ai, settings, src.id)
            answers = _answers_for(structure, section)
            if text_layer and section.solutions_first_page and section.solutions_last_page:
                exact = answers_from_solutions(pdf, section.solutions_first_page, section.solutions_last_page)
                for n, a in exact.items():
                    if answers.get(n) not in (None, "", a):
                        log.warning("answer for Q%s: Claude read %r, solutions say %r; using solutions",
                                    n, answers[n], a)
                answers.update(exact)
            for n in sorted(crops):
                boxes = crops[n]
                analysis = ai.structured(QuestionAnalysis, ANALYSE_SYSTEM, [b.path for b in boxes],
                                         f"Allowed technique tags:\n{_tag_list()}", "low")
                raw = answers.get(n, "")
                answer = normalise(raw, analysis.answer_type) or raw
                problem = Problem(transcription=analysis.transcription, answer=answer,
                                  answer_type=analysis.answer_type, tags=analysis.tags)
                db.add(problem)
                db.flush()
                part, points, penalty = _points_for(section, n)
                figs = _figures(pdf, [b.as_list() for b in boxes], out_dir, n, settings) if text_layer else []
                db.add(PaperQuestion(
                    paper_id=paper.id, number=n, part=part, points=points, penalty=penalty or None,
                    show_original=analysis.picture_based or None, problem_id=problem.id,
                    crop_paths=[str(b.path.relative_to(settings.data_dir)) for b in boxes],
                    crop_boxes=[b.as_list() for b in boxes], figure_paths=figs))
                db.commit()
        link_duplicates(db, src.id)
        src.status = ImportStatus.done
    except Exception as e:  # never leave the import stuck in "running"
        log.exception("import failed")
        db.rollback()
        src = db.get(SourcePdf, source_pdf_id)
        src.status, src.error = ImportStatus.failed, _plain(e)
    db.commit()


def _figures(pdf: Path, boxes: list[list], out_dir: Path, n: int, settings: Settings) -> list[str]:
    try:
        found = extract_figures(pdf, boxes, out_dir, f"q{n:03}")
    except Exception:
        log.exception("figure extraction failed for question %s", n)
        return []
    return [str(p.relative_to(settings.data_dir)) for p in found]


def backfill_figures(session_factory, settings: Settings) -> int:
    """Extract figures for questions imported before figure support existed. Returns how many were done."""
    db = session_factory()
    done = 0
    try:
        for q in db.query(PaperQuestion).filter(PaperQuestion.figure_paths.is_(None)).all():
            pdf = Path(q.paper.source_pdf.path)
            if not pdf.exists() or not q.crop_boxes or not has_text_layer(pdf):
                q.figure_paths = []
            else:
                out_dir = crop_dir(settings, q.paper)
                q.figure_paths = _figures(pdf, q.crop_boxes, out_dir, q.number, settings)
            done += 1
        db.commit()
    finally:
        db.close()
    return done
