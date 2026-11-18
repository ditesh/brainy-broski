import re

import pytest

from app.ai.client import AIError
from app.ai.schemas import PageBoxes, PdfStructure, QuestionAnalysis
from app.importer.pipeline import detect_structure, run_import
from app.models import ImportStatus, Paper, PaperQuestion, Problem, SourcePdf
from tests.fixtures.make_pdf import (build_contest_pdf, build_image_only_pdf, contest_layout,
                                     contest_structure_dict, question_text)

CROP_RE = re.compile(r"/(?P<cat>[^/]+)/q(?P<n>\d{3})-0\.png$")


def analysis_responder(call):
    m = CROP_RE.search(str(call.images[0]))
    return QuestionAnalysis(transcription=question_text(m["cat"], int(m["n"])),
                            answer_type="integer", tags=["parity"])


@pytest.fixture
def src(db, settings, tmp_path):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    path = build_contest_pdf(settings.data_dir / "c.pdf", contest_layout())
    s = SourcePdf(filename="c.pdf", path=str(path), contest="IMONST", year=2020, duration_min=180,
                  structure=contest_structure_dict(), status=ImportStatus.needs_review)
    db.add(s)
    db.commit()
    return s


@pytest.fixture
def ai(fake_ai):
    return fake_ai.respond(QuestionAnalysis, analysis_responder)


def pq(db, category, n):
    return (db.query(PaperQuestion).join(Paper)
            .filter(Paper.category == category, PaperQuestion.number == n).one())


def test_detect_structure_stores_and_marks_needs_review(db, settings, fake_ai, src):
    src.structure, src.status = None, ImportStatus.pending
    db.commit()
    fake_ai.add(PdfStructure, PdfStructure.model_validate(contest_structure_dict()))
    detect_structure(src.id, db, fake_ai, settings)
    assert src.status == ImportStatus.needs_review
    assert src.structure["sections"][2]["category"] == "Junior"
    assert len(fake_ai.last_call.images) == 14


def test_detect_structure_failure_marks_failed(db, settings, fake_ai, src):
    fake_ai.add(PdfStructure, AIError("boom"))
    detect_structure(src.id, db, fake_ai, settings)
    assert src.status == ImportStatus.failed and "boom" in src.error


def test_import_creates_papers_for_ticked_categories(db, settings, ai, src):
    run_import(src.id, ["Junior"], db, ai, settings)
    assert [p.category for p in db.query(Paper)] == ["Junior"]
    assert db.query(PaperQuestion).count() == 20
    assert src.status == ImportStatus.done


def test_answers_come_from_key(db, settings, ai, src):
    run_import(src.id, ["Junior"], db, ai, settings)
    assert pq(db, "Junior", 1).problem.answer == "18"
    assert pq(db, "Junior", 7).problem.answer == "121"


def test_points_from_parts(db, settings, ai, src):
    run_import(src.id, ["Junior"], db, ai, settings)
    assert pq(db, "Junior", 16).points == 4 and pq(db, "Junior", 1).points == 1
    assert pq(db, "Junior", 16).part == "Part D"


def test_crops_saved(db, settings, ai, src):
    run_import(src.id, ["Junior"], db, ai, settings)
    q = pq(db, "Junior", 3)
    assert q.crop_paths and (settings.data_dir / q.crop_paths[0]).exists()
    assert not q.crop_paths[0].startswith("/")
    assert q.crop_boxes[0][0] == 9


def test_duplicates_linked_across_categories(db, settings, ai, src):
    run_import(src.id, ["Primary", "Junior"], db, ai, settings)
    assert pq(db, "Junior", 1).problem_id == pq(db, "Primary", 6).problem_id
    assert pq(db, "Junior", 6).problem_id != pq(db, "Primary", 6).problem_id
    assert db.query(Problem).count() == 35


def test_ai_failure_marks_failed_and_nothing_published(db, settings, fake_ai, src):
    fake_ai.add(QuestionAnalysis, AIError("rate limited"))
    run_import(src.id, ["Junior"], db, fake_ai, settings)
    assert src.status == ImportStatus.failed and "rate limited" in src.error
    assert all(not p.published for p in db.query(Paper))


def test_retry_does_not_duplicate(db, settings, ai, src):
    run_import(src.id, ["Junior"], db, ai, settings)
    run_import(src.id, ["Junior"], db, ai, settings)
    assert db.query(Paper).count() == 1 and db.query(PaperQuestion).count() == 20


def test_malay_sections_never_imported(db, settings, ai, src):
    run_import(src.id, ["Primary", "Junior"], db, ai, settings)
    assert all(p.language == "en" for p in db.query(Paper))
    assert db.query(Paper).count() == 2


def test_scanned_pdf_uses_ai_boxes(db, settings, fake_ai, tmp_path):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    path = build_image_only_pdf(settings.data_dir / "scan.pdf")
    s = SourcePdf(filename="scan.pdf", path=str(path), contest="X", year=2021, status=ImportStatus.needs_review,
                  structure={"sections": [{"category": "Junior", "language": "en", "first_page": 1, "last_page": 1,
                                           "parts": []}],
                             "answer_keys": [{"category": "Junior", "page": 1,
                                              "answers": [{"question": 1, "answer": "7"}]}]})
    db.add(s)
    db.commit()
    fake_ai.add(PageBoxes, PageBoxes(boxes=[{"number": 1, "x0": 0.1, "y0": 0.05, "x1": 0.9, "y1": 0.15}]))
    fake_ai.add(QuestionAnalysis, QuestionAnalysis(transcription="q", answer_type="integer", tags=[]))
    run_import(s.id, ["Junior"], db, fake_ai, settings)
    q = db.query(PaperQuestion).one()
    assert q.problem.answer == "7" and q.points == 1 and (settings.data_dir / q.crop_paths[0]).exists()


def test_unexpected_error_in_structure_marks_failed(db, settings, fake_ai, src):
    fake_ai.add(PdfStructure, RuntimeError("weird"))
    detect_structure(src.id, db, fake_ai, settings)
    assert src.status == ImportStatus.failed and "weird" in src.error


def test_unexpected_error_in_import_marks_failed(db, settings, fake_ai, src):
    fake_ai.add(QuestionAnalysis, RuntimeError("weird"))
    run_import(src.id, ["Junior"], db, fake_ai, settings)
    db.refresh(src)
    assert src.status == ImportStatus.failed
