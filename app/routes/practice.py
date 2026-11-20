from collections import defaultdict

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import require_user
from app.goals import goal_status
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


def child_goal(request: Request, db: Session, user: User):
    """This week's goal for a child (None for parents)."""
    if user.role != Role.child:
        return None
    from app import daily
    tz = request.app.state.settings.timezone
    return goal_status(db, user, daily.local_today(tz), tz)


@router.get("/practice")
def practice_home(request: Request, contest: str = "", level: str = "", user: User = Depends(require_user),
                  db: Session = Depends(get_db)):
    return render_home(request, db, user, contest, level)


def render_home(request: Request, db: Session, user: User, contest: str = "", level: str = "",
                status_code: int = 200, **extra):
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
    new_bonus = _settle_and_announce(request, db, user)
    goal, buddy_pet = child_goal(request, db, user), _buddy(db, user)
    mission = lines = brain = None
    if user.role == Role.child:
        from app.games import rounds_left
        brain = rounds_left(db, user, request.app.state.settings.timezone)
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from app.mission import buddy_lines, mission_for
        mission = mission_for(db, user, shown)
        now = datetime.now(ZoneInfo(request.app.state.settings.timezone))
        lines = buddy_lines(user, buddy_pet, goal, mission, now)
    return render(request, "practice_home.html", status_code=status_code, new_bonus=new_bonus,
                  mission=mission, buddy_lines=lines, brain=brain,
                  wonder_hidden=request.session.get("wonder_hidden") == today, goal=goal,
                  buddy=buddy_pet,
                  contests=contests, contest=contest, levels=choices,
                  level=level, shown=shown, in_progress=in_progress, done=done, status=paper_status(db, user),
                  number_fact=_fav_number_fact(user), **extra)


def _settle_and_announce(request: Request, db: Session, user: User):
    """Give any bonus egg he has earned, and announce each one once (per device) on the home page."""
    if user.role != Role.child:
        return None
    from app import daily
    from app.models import PetBonus
    from app.pets.creatures import CREATURES
    from app.pets.growth import growth, settle_recent
    tz = request.app.state.settings.timezone
    settle_recent(db, user, daily.local_today(tz), tz)
    seen = set(request.session.get("seen_bonus", []))
    fresh = (db.query(PetBonus).filter(PetBonus.user_id == user.id).order_by(PetBonus.id.desc()).first())
    if fresh is None or fresh.id in seen:
        return None
    request.session["seen_bonus"] = sorted(seen | {fresh.id})[-20:]
    return {"c": CREATURES[fresh.tag], "amount": fresh.amount, "stage": growth(db, user)[fresh.tag].stage}


def _buddy(db: Session, user: User):
    if user.role != Role.child:
        return None
    from app.pets.creatures import CREATURES
    from app.pets.growth import buddy, growth
    states = growth(db, user)
    tag = buddy(db, user, states)
    return {"c": CREATURES[tag], "stage": states[tag].stage} if tag else None


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


@router.post("/mission/start")
def mission_start(paper_id: int = Form(...), numbers: str = Form(""), user: User = Depends(require_user),
                  db: Session = Depends(get_db)):
    if user.role != Role.child:
        raise HTTPException(403)
    paper = db.get(Paper, paper_id)
    if paper is None or not paper.published:
        raise HTTPException(404)
    try:
        chosen = [int(n) for n in numbers.split(",") if n.strip()]
        a = start_attempt(db, user, paper, "practice", chosen or [-1])
    except ValueError:
        raise HTTPException(400, "That mission isn't available any more. Pick a paper below.")
    return RedirectResponse(f"/attempts/{a.id}?q={a.question_numbers[0]}", status_code=303)


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
    from app import daily
    from app.pets.celebrate import celebration
    tz = request.app.state.settings.timezone
    cel = celebration(db, user, a, daily.local_today(tz), tz)
    return render(request, "results.html", a=a, rows=rows, misses=misses(a), is_owner=a.user_id == user.id,
                  stars=stars, redo_count=sum(1 for r in a.responses if r.correct_first is False), cel=cel)


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
