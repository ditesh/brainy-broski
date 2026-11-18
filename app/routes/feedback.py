from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.ai.client import AIClient, get_ai
from app.auth import require_parent, require_user
from app.db import get_db
from app.diagnosis.service import enqueue_diagnosis
from app.followups import answer_followup, followups_for_card
from app.models import Label, Paper, PaperQuestion, Response, Role, Technique, User
from app.practice.service import misses
from app.routes.practice import get_attempt, get_response
from app.techniques import TECHNIQUES
from app.web import render

router = APIRouter()
LABEL_TEXT = {
    "careless_self_corrected": "Careless slip (you fixed it)",
    "careless": "Careless slip",
    "technique": "Technique to learn",
    "unsure": "Not sure",
}


def parent_name(db: Session) -> str:
    p = db.query(User).filter(User.role == Role.parent).order_by(User.id).first()
    return p.display_name if p else "your parent"


def technique_info(db: Session, tag: str | None) -> dict | None:
    if not tag:
        return None
    t = db.get(Technique, tag)
    if t:
        return {"tag": t.tag, "name": t.name, "description": t.kid_description}
    for tg, name, desc in TECHNIQUES:
        if tg == tag:
            return {"tag": tg, "name": name, "description": desc}
    return None


def card_context(request: Request, db: Session, r: Response, user: User) -> dict:
    d = r.diagnosis or {}
    label = (r.parent_override or r.label)
    tag = d.get("technique_tag")
    followups = []
    if label == Label.technique and tag and r.attempt.user_id == user.id:
        followups = followups_for_card(db, user, r, tag)
    return {
        "r": r, "q": r.paper_question, "problem": r.paper_question.problem, "d": d,
        "label": label.value if label else None, "label_text": LABEL_TEXT, "parent_name": parent_name(db),
        "technique": technique_info(db, d.get("technique_tag")), "is_parent": user.role == Role.parent,
        "followups": followups, "show_followups": label == Label.technique and bool(tag),
    }


def _submitted_response(db: Session, response_id: int, user: User) -> Response:
    r = get_response(db, response_id, user, allow_parent=True)
    if r.attempt.submitted_at is None:
        raise HTTPException(404)
    return r


@router.get("/responses/{response_id}/feedback")
def response_feedback(response_id: int, request: Request, user: User = Depends(require_user),
                      db: Session = Depends(get_db)):
    r = _submitted_response(db, response_id, user)
    ctx = card_context(request, db, r, user)
    if request.headers.get("HX-Request"):
        return render(request, "_feedback_card.html", c=ctx)
    return render(request, "feedback.html", cards=[ctx], attempt=r.attempt)


@router.get("/attempts/{attempt_id}/feedback")
def attempt_feedback(attempt_id: int, request: Request, user: User = Depends(require_user),
                     db: Session = Depends(get_db)):
    a = get_attempt(db, attempt_id, user, allow_parent=True)
    if a.submitted_at is None:
        raise HTTPException(404)
    cards = [card_context(request, db, r, user)
             for r in sorted(misses(a), key=lambda r: r.paper_question.number)]
    return render(request, "feedback.html", cards=cards, attempt=a)


@router.post("/parent/responses/{response_id}/rediagnose")
def rediagnose(response_id: int, request: Request, background: BackgroundTasks,
               user: User = Depends(require_parent), db: Session = Depends(get_db), ai: AIClient = Depends(get_ai)):
    r = _submitted_response(db, response_id, user)
    p = r.paper_question.problem
    if p.verified is False:
        p.verified = None  # allow another solve attempt
    enqueue_diagnosis(background, request.app, db, r)
    return RedirectResponse(f"/responses/{r.id}/feedback", status_code=303)


@router.post("/responses/{response_id}/followups/{pq_id}")
def followup_answer(response_id: int, pq_id: int, request: Request, answer: str = Form(""),
                    user: User = Depends(require_user), db: Session = Depends(get_db)):
    r = get_response(db, response_id, user)  # owner only
    if r.attempt.submitted_at is None:
        raise HTTPException(404)
    pq = db.get(PaperQuestion, pq_id)
    if pq is None or not pq.paper.published or not answer.strip():
        raise HTTPException(400)
    f = answer_followup(db, user, r, pq, answer)
    return render(request, "_followup.html", f={"pq": pq, "done": f}, r=r, parent_name=parent_name(db))
