import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.answers import normalise
from app.auth import require_parent
from app.db import get_db
from app.models import AnswerType, Paper, PaperQuestion, Problem, User
from app.pdf.render import crop_box
from app.techniques import TECHNIQUE_TAGS
from app.web import render

router = APIRouter()


def _get_pq(db: Session, pq_id: int) -> PaperQuestion:
    q = db.get(PaperQuestion, pq_id)
    if q is None:
        raise HTTPException(404)
    return q


def _shared_with(db: Session, q: PaperQuestion) -> list[PaperQuestion]:
    return (db.query(PaperQuestion).filter(PaperQuestion.problem_id == q.problem_id,
                                           PaperQuestion.id != q.id).all())


def _candidates(db: Session, q: PaperQuestion) -> list[PaperQuestion]:
    """Questions in other papers of the same PDF with the same answer that aren't linked yet."""
    key = normalise(q.problem.answer, q.problem.answer_type) or q.problem.answer
    others = (db.query(PaperQuestion).join(Paper)
              .filter(Paper.source_pdf_id == q.paper.source_pdf_id, Paper.id != q.paper_id,
                      PaperQuestion.problem_id != q.problem_id).all())
    return [o for o in others if (normalise(o.problem.answer, o.problem.answer_type) or o.problem.answer) == key]


def _ctx(db: Session, q: PaperQuestion) -> dict:
    return {"q": q, "shared": _shared_with(db, q), "candidates": _candidates(db, q), "version": _version(q)}


def _card(request: Request, db: Session, q: PaperQuestion, error: str | None = None, status_code: int = 200):
    return render(request, "_review_question.html", status_code=status_code, answer_types=list(AnswerType),
                  error=error, **_ctx(db, q))


def _version(q: PaperQuestion) -> str:
    return hashlib.md5(repr(q.crop_boxes).encode()).hexdigest()[:8]


@router.get("/parent/papers/{paper_id}/review")
def review(paper_id: int, request: Request, user: User = Depends(require_parent), db: Session = Depends(get_db)):
    paper = db.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(404)
    cards = [_ctx(db, q) for q in paper.questions]
    return render(request, "review.html", paper=paper, cards=cards, answer_types=list(AnswerType))


@router.post("/parent/questions/{pq_id}")
def update_question(pq_id: int, request: Request, answer: str = Form(...), answer_type: AnswerType = Form(...),
                    points: int = Form(...), tags: str = Form(""), user: User = Depends(require_parent),
                    db: Session = Depends(get_db)):
    q = _get_pq(db, pq_id)
    p = q.problem
    p.answer_type = answer_type
    p.answer = normalise(answer, answer_type) or answer.strip()
    p.tags = [t for t in (x.strip() for x in tags.split(",")) if t in TECHNIQUE_TAGS][:3]
    p.verified, p.reference_solution = None, None  # answer may have changed; re-verify later
    q.points = max(0, points)
    db.commit()
    return _card(request, db, q)


@router.post("/parent/questions/{pq_id}/crop")
def nudge_crop(pq_id: int, request: Request, dy0: float = Form(0), dy1: float = Form(0),
               user: User = Depends(require_parent), db: Session = Depends(get_db)):
    q = _get_pq(db, pq_id)
    settings = request.app.state.settings
    boxes = [list(b) for b in q.crop_boxes]
    boxes[0][2] = max(0.0, boxes[0][2] + dy0)
    boxes[-1][4] = boxes[-1][4] + dy1
    pdf = Path(q.paper.source_pdf.path)
    for b, rel in zip(boxes, q.crop_paths):
        if b[4] - b[2] < 10:
            return _card(request, db, q, error="That would make the picture too small.", status_code=400)
        crop_box(pdf, int(b[0]), (b[1], b[2], b[3], b[4]), settings.data_dir / rel)
    q.crop_boxes = boxes
    db.commit()
    return _card(request, db, q)


@router.post("/parent/questions/{pq_id}/unlink")
def unlink(pq_id: int, request: Request, user: User = Depends(require_parent), db: Session = Depends(get_db)):
    q = _get_pq(db, pq_id)
    if _shared_with(db, q):
        old = q.problem
        new = Problem(transcription=old.transcription, answer=old.answer, answer_type=old.answer_type,
                      tags=list(old.tags), reference_solution=old.reference_solution, verified=old.verified)
        db.add(new)
        db.flush()
        q.problem_id = new.id
        db.commit()
        db.refresh(q)
    return _card(request, db, q)


@router.post("/parent/questions/{pq_id}/link")
def link(pq_id: int, request: Request, other_pq_id: int = Form(...), user: User = Depends(require_parent),
         db: Session = Depends(get_db)):
    q, other = _get_pq(db, pq_id), _get_pq(db, other_pq_id)
    a = normalise(q.problem.answer, q.problem.answer_type) or q.problem.answer
    b = normalise(other.problem.answer, other.problem.answer_type) or other.problem.answer
    if a != b:
        return _card(request, db, q, status_code=400,
                     error="These two questions have different answers, so they can't be the same question.")
    old_id = q.problem_id
    if old_id != other.problem_id:
        q.problem_id = other.problem_id
        db.flush()
        if not db.query(PaperQuestion).filter_by(problem_id=old_id).count():
            db.delete(db.get(Problem, old_id))
        db.commit()
        db.refresh(q)
    return _card(request, db, q)


@router.post("/parent/papers/{paper_id}/publish")
def publish(paper_id: int, user: User = Depends(require_parent), db: Session = Depends(get_db)):
    paper = db.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(404)
    paper.published = True
    db.commit()
    return RedirectResponse(f"/parent/papers/{paper.id}/review", status_code=303)


@router.post("/parent/papers/{paper_id}/unpublish")
def unpublish(paper_id: int, user: User = Depends(require_parent), db: Session = Depends(get_db)):
    paper = db.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(404)
    paper.published = False
    db.commit()
    return RedirectResponse(f"/parent/papers/{paper.id}/review", status_code=303)
