from collections import defaultdict

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import require_user
from app.db import get_db
from app.models import Attempt, Paper, Response, Role, SourcePdf, User
from app.practice.service import (deadline, is_expired, misses, paper_status, response_for, save_answer,
                                  start_attempt, start_redo, submit, submit_retry)
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
def practice_home(request: Request, contest: str = "", level: str = "", user: User = Depends(require_user),
                  db: Session = Depends(get_db)):
    papers = (db.query(Paper).join(SourcePdf).filter(Paper.published.is_(True))
              .order_by(SourcePdf.year.desc(), Paper.id).all())
    attempts = db.query(Attempt).filter_by(user_id=user.id).order_by(Attempt.started_at.desc()).all()
    # levels per competition, in the order the papers list them (e.g. Primary, Junior, Senior)
    levels: dict[str, list[str]] = {}
    for p in sorted(papers, key=lambda p: p.id):
        lv = levels.setdefault(p.source_pdf.contest, [])
        if p.category not in lv:
            lv.append(p.category)
    contests = sorted(levels)
    last = next((a.paper for a in attempts if a.paper.published and a.paper.source_pdf.contest in levels), None)
    if contest not in levels:
        contest = last.source_pdf.contest if last else (contests[0] if contests else "")
    choices = levels.get(contest, [])
    if level not in choices:
        if last and last.source_pdf.contest == contest:
            level = last.category
        else:
            level = "Junior" if "Junior" in choices else (choices[0] if choices else "")
    shown = sorted((p for p in papers if p.source_pdf.contest == contest and p.category == level),
                   key=lambda p: -(p.year or p.source_pdf.year or 0))
    in_progress = [a for a in attempts if a.submitted_at is None]
    done = [a for a in attempts if a.submitted_at is not None][:10]
    from app import daily
    today = daily.local_today(request.app.state.settings.timezone).isoformat()
    return render(request, "practice_home.html", wonder_hidden=request.session.get("wonder_hidden") == today,
                  contests=contests, contest=contest, levels=choices,
                  level=level, shown=shown, in_progress=in_progress, done=done, status=paper_status(db, user),
                  number_fact=_fav_number_fact(user))


def _fav_number_fact(user: User) -> str:
    from app.profile import number_fact
    n = (user.profile or {}).get("favourite_number")
    return number_fact(n) if isinstance(n, int) else ""


@router.post("/wonder/dismiss")
def wonder_dismiss(request: Request, user: User = Depends(require_user)):
    from fastapi.responses import HTMLResponse
    from app import daily
    request.session["wonder_hidden"] = daily.local_today(request.app.state.settings.timezone).isoformat()
    if request.headers.get("HX-Request"):
        return HTMLResponse("")
    return RedirectResponse("/practice", status_code=303)


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
                  stars=stars, redo_count=sum(1 for r in a.responses if r.correct_first is False))


@router.post("/attempts/{attempt_id}/redo")
def attempt_redo(attempt_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)):
    a = get_attempt(db, attempt_id, user)
    try:
        redo = start_redo(db, a)
    except ValueError:
        raise HTTPException(400, "There are no misses to redo on this paper.")
    return RedirectResponse(f"/attempts/{redo.id}?q={redo.question_numbers[0]}", status_code=303)


@router.post("/responses/{response_id}/retry")
def response_retry(response_id: int, answer: str = Form(""), user: User = Depends(require_user),
                   db: Session = Depends(get_db)):
    r = get_response(db, response_id, user)
    try:
        submit_retry(db, r, answer)
    except ValueError:
        pass
    return RedirectResponse(f"/attempts/{r.attempt_id}/results#r{r.id}", status_code=303)
