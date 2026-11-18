import difflib

from sqlalchemy.orm import Session

from app.answers import normalise
from app.models import Paper, PaperQuestion, Problem

SIMILARITY = 0.9


def _norm_text(s: str) -> str:
    return " ".join(s.split()).casefold()


def link_duplicates(db: Session, source_pdf_id: int) -> int:
    """Within one source PDF, make identical questions share the lowest-id Problem."""
    pqs = (db.query(PaperQuestion).join(Paper).filter(Paper.source_pdf_id == source_pdf_id)
           .order_by(PaperQuestion.problem_id).all())
    canonical: list[Problem] = []
    merged = 0
    for q in pqs:
        p = q.problem
        key = normalise(p.answer, p.answer_type) or p.answer
        match = None
        for c in canonical:
            if c.id == p.id:
                match = c
                break
            ckey = normalise(c.answer, c.answer_type) or c.answer
            if ckey == key and difflib.SequenceMatcher(
                    None, _norm_text(c.transcription), _norm_text(p.transcription)).ratio() >= SIMILARITY:
                match = c
                break
        if match is None:
            canonical.append(p)
        elif match.id != p.id:
            q.problem_id = match.id
            db.flush()
            if not db.query(PaperQuestion).filter(PaperQuestion.problem_id == p.id).count():
                db.delete(p)
            merged += 1
    db.commit()
    return merged
