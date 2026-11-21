"""The pet's help during practice: an instant hint from the question's technique, and (only when asked) a first
step and a checked solution written by Claude, saved on the problem so every later ask is instant."""
import logging
import re
import threading
from typing import Callable

from fastapi import FastAPI

from app.ai.client import ensure_ai
from app.diagnosis.service import ensure_reference_solution
from app.models import PaperQuestion, Problem
from app.techniques import TECHNIQUES

log = logging.getLogger(__name__)
_ORDER = {t: (i, name, about) for i, (t, name, about) in enumerate(TECHNIQUES)}
_inflight: set[int] = set()       # problems Claude is solving right now
_errors: dict[int, str] = {}      # problems whose last solve couldn't reach Claude (cleared on the next ask)
_lock = threading.Lock()
FOGGY = "My brain's foggy — try again in a bit."


def hint_one(problem: Problem) -> str:
    known = sorted((_ORDER[t] for t in (problem.tags or []) if t in _ORDER), key=lambda x: x[0])
    if not known:
        return "Read it again slowly and draw a picture!"
    _, name, about = known[0]
    return f"This one smells like {name.lower()}! 🕵️ {about}"


def first_step(solution: str | None) -> str:
    line = (solution or "").strip().split("\n", 1)[0]
    return re.sub(r"^\s*\d+\.\s*", "", line).strip()


def solution_state(problem: Problem) -> str:
    return {True: "ready", False: "failed"}.get(problem.verified, "missing")


def state_for(problem: Problem) -> str:
    """ready | failed | thinking | foggy | missing"""
    s = solution_state(problem)
    if s != "missing":
        return s
    if problem.id in _inflight:
        return "thinking"
    return "foggy" if problem.id in _errors else "missing"


def clear_error(problem_id: int) -> None:
    _errors.pop(problem_id, None)


def request_solve(app: FastAPI, problem_id: int, schedule: Callable) -> bool:
    """Start one background solve for this problem unless one is already running. schedule(fn) runs fn later."""
    with _lock:
        if problem_id in _inflight:
            return False
        _inflight.add(problem_id)
        _errors.pop(problem_id, None)
    schedule(lambda: _solve(app, problem_id))
    return True


def _solve(app: FastAPI, problem_id: int) -> None:
    db = app.state.session_factory()
    try:
        problem = db.get(Problem, problem_id)
        pq = db.query(PaperQuestion).filter(PaperQuestion.problem_id == problem_id).first()
        crops = [app.state.settings.data_dir / p for p in (pq.crop_paths if pq else [])]
        ensure_reference_solution(db, problem, crops, ensure_ai(app))
        if problem.verified is None:
            _errors[problem_id] = getattr(problem, "_last_error", "unreachable")
    except Exception:
        log.exception("solving problem %s for a hint failed", problem_id)
        _errors[problem_id] = "crashed"
    finally:
        _inflight.discard(problem_id)
        db.close()
