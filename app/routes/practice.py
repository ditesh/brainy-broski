from collections import defaultdict

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import require_user
from app.db import get_db
from app.models import Attempt, Paper, Response, Role, SourcePdf, User
from app.practice.service import (deadline, is_expired, misses, response_for, save_answer, start_attempt,
                                  submit, submit_retry)
from app.web import render

router = APIRouter()


def get_attempt(db: Session, attempt_id: int, user: User, allow_parent: bool = False) -> Attempt:
    a = db.get(Attempt, attempt_id)
    if a is None:
        raise HTTPException(404)
    if a.user_id != user.id and not (allow_parent and user.role == Role.parent):
        raise HTTPException(404)
    db.refresh(a)
    return a


def get_response(db: Session, response_id: int, user: User, allow_parent: bool = False) -> Response:
    r = db.get(Response, response_id)
    if r is None:
        raise HTTPException(404)
    get_attempt(db, r.attempt_id, user, allow_parent)
    db.refresh(r)
    return r


@router.get("/practice")
def practice_home(request: Request, category: str = "Junior", user: User = Depends(require_user),
                  db: Session = Depends(get_db)):
    papers = (db.query(Paper).join(SourcePdf).filter(Paper.published.is_(True))
              .order_by(SourcePdf.contest, SourcePdf.year.desc(), Paper.category).all())
    categories = sorted({p.category for p in papers})
    if category != "All" and category not in categories:
        category = "All"
    shown = [p for p in papers if category == "All" or p.category == category]
    grouped: dict[str, list[Paper]] = defaultdict(list)
    for p in shown:
        grouped[p.source_pdf.contest].append(p)
    attempts = db.query(Attempt).filter_by(user_id=user.id).order_by(Attempt.started_at.desc()).all()
    in_progress = [a for a in attempts if a.submitted_at is None]
    done = [a for a in attempts if a.submitted_at is not None][:10]
    return render(request, "practice_home.html", grouped=grouped, categories=categories, category=category,
                  in_progress=in_progress, done=done)


@router.post("/practice/start")
def practice_start(paper_id: int = Form(...), mode: str = Form("practice"), part: str = Form(""),
                   user: User = Depends(require_user), db: Session = Depends(get_db)):
    paper = db.get(Paper, paper_id)
    if paper is None or not paper.published:
        raise HTTPException(404)
    numbers = [q.number for q in paper.questions if q.part == part] if part else None
    if part and not numbers:
        raise HTTPException(400, "No questions in that part.")
    try:
        a = start_attempt(db, user, paper, mode, numbers)
    except ValueError:
        raise HTTPException(400, "No questions in that part.")
    return RedirectResponse(f"/attempts/{a.id}?q={a.question_numbers[0]}", status_code=303)


def _expire_if_needed(db: Session, a: Attempt) -> bool:
    if a.submitted_at is None and is_expired(a):
        submit(db, a)
        return True
    return False


@router.get("/attempts/{attempt_id}")
def attempt_page(attempt_id: int, request: Request, q: int | None = None, user: User = Depends(require_user),
                 db: Session = Depends(get_db)):
    a = get_attempt(db, attempt_id, user)
    _expire_if_needed(db, a)
    if a.submitted_at is not None:
        return RedirectResponse(f"/attempts/{a.id}/results", status_code=303)
    numbers = a.question_numbers
    current = q if q in numbers else numbers[0]
    r = response_for(a, current)
    idx = numbers.index(current)
    answered = {resp.paper_question.number for resp in a.responses if resp.first_answer}
    d = deadline(a)
    return render(request, "attempt.html", a=a, r=r, pq=r.paper_question, numbers=numbers, current=current,
                  prev=numbers[idx - 1] if idx > 0 else None,
                  next=numbers[idx + 1] if idx + 1 < len(numbers) else None,
                  answered=answered, deadline=d.isoformat() + "Z" if d else None)


@router.post("/attempts/{attempt_id}/answer")
def attempt_answer(attempt_id: int, q: int = Form(...), answer: str = Form(""), go: str = Form(""),
                   user: User = Depends(require_user), db: Session = Depends(get_db)):
    a = get_attempt(db, attempt_id, user)
    if _expire_if_needed(db, a) or a.submitted_at is not None:
        return RedirectResponse(f"/attempts/{a.id}/results", status_code=303)
    try:
        save_answer(db, a, q, answer)
    except ValueError:
        raise HTTPException(400)
    if go == "submit":
        submit(db, a)
        return RedirectResponse(f"/attempts/{a.id}/results", status_code=303)
    target = int(go) if go.isdigit() and int(go) in a.question_numbers else q
    return RedirectResponse(f"/attempts/{a.id}?q={target}", status_code=303)


@router.post("/attempts/{attempt_id}/submit")
def attempt_submit(attempt_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)):
    a = get_attempt(db, attempt_id, user)
    submit(db, a)
    return RedirectResponse(f"/attempts/{a.id}/results", status_code=303)


@router.get("/attempts/{attempt_id}/results")
def attempt_results(attempt_id: int, request: Request, user: User = Depends(require_user),
                    db: Session = Depends(get_db)):
    a = get_attempt(db, attempt_id, user, allow_parent=True)
    _expire_if_needed(db, a)
    if a.submitted_at is None:
        raise HTTPException(404)
    rows = sorted(a.responses, key=lambda r: r.paper_question.number)
    pct = (a.score / a.max_score) if a.max_score else 0
    stars = 3 if pct >= 0.9 else 2 if pct >= 0.6 else 1 if pct >= 0.3 else 0
    return render(request, "results.html", a=a, rows=rows, misses=misses(a), is_owner=a.user_id == user.id,
                  stars=stars)


@router.post("/responses/{response_id}/retry")
def response_retry(response_id: int, answer: str = Form(""), user: User = Depends(require_user),
                   db: Session = Depends(get_db)):
    r = get_response(db, response_id, user)
    try:
        submit_retry(db, r, answer)
    except ValueError:
        pass
    return RedirectResponse(f"/attempts/{r.attempt_id}/results#r{r.id}", status_code=303)
