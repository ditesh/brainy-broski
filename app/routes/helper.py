"""The burrow pet's help on a practice question: hint, another hint (first step), solution."""
from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth import require_user
from app.db import get_db
from app.helper import FOGGY, clear_error, first_step, hint_one, request_solve, state_for
from app.models import User
from app.practice.service import give_up, response_for
from app.routes.practice import _practice_attempt
from app.web import render

router = APIRouter()
KINDS = ("hint", "hint2", "solution")


def _say(request: Request, background: BackgroundTasks, a, r, kind: str):
    problem = r.paper_question.problem
    ctx = {"a": a, "q": r.paper_question.number, "kind": kind, "answer": problem.answer, "foggy": FOGGY}
    if kind == "hint":
        return render(request, "_burrow_say.html", state="ready", text=hint_one(problem), **ctx)
    state = state_for(problem)
    if state == "missing":
        request_solve(request.app, problem.id, background.add_task)
        state = "thinking"
    elif state == "foggy":
        clear_error(problem.id)  # the next ask tries Claude again
    return render(request, "_burrow_say.html", state=state, step=first_step(problem.reference_solution),
                  solution=problem.reference_solution, **ctx)


def _start(db: Session, attempt_id: int, user: User, q: int, kind: str):
    if kind not in KINDS:
        raise HTTPException(400)
    a, done = _practice_attempt(db, attempt_id, user, q)
    if done:  # handed in: send the whole page to the results
        return a, None, Response(status_code=200, headers={"HX-Redirect": done.headers["location"]})
    return a, response_for(a, q), None


@router.post("/attempts/{attempt_id}/help")
def ask_pet(attempt_id: int, request: Request, background: BackgroundTasks, q: int = Form(...),
            kind: str = Form(...), answer: str = Form(""), user: User = Depends(require_user),
            db: Session = Depends(get_db)):
    a, r, done = _start(db, attempt_id, user, q, kind)
    if done:
        return done
    if kind == "hint":
        r.hints_used = max(r.hints_used or 0, 1)
    elif kind == "hint2":
        r.hints_used = 2
    else:
        if not r.locked:
            give_up(db, a, q, answer)
        r.solution_seen = True
    db.commit()
    resp = _say(request, background, a, r, kind)
    if kind == "solution":
        resp.headers["HX-Trigger"] = "bb-locked"
    return resp


@router.get("/attempts/{attempt_id}/help")
def pet_thinking(attempt_id: int, request: Request, background: BackgroundTasks, q: int, kind: str,
                 user: User = Depends(require_user), db: Session = Depends(get_db)):
    """Polled while the pet is thinking; no side effects beyond (re)starting a missing solve."""
    a, r, done = _start(db, attempt_id, user, q, kind)
    if done:
        return done
    db.refresh(r.paper_question.problem)
    return _say(request, background, a, r, kind)
