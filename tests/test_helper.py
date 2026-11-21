"""The pet's help in practice: an instant hint, then a first step and a checked solution from Claude on request."""
import re

import pytest

from app import helper
from app.ai.client import AIError
from app.ai.schemas import ReferenceSolution
from app.helper import first_step, hint_one, request_solve, solution_state
from app.models import Attempt, Problem
from app.practice.service import response_for, start_attempt


def _q(paper, n):
    return next(q for q in paper.questions if q.number == n)


@pytest.fixture(autouse=True)
def _clean():
    helper._inflight.clear()
    helper._errors.clear()
    yield
    helper._inflight.clear()
    helper._errors.clear()


@pytest.fixture
def att(db, child, junior_paper):
    p = _q(junior_paper, 1).problem
    p.tags, p.reference_solution, p.verified = ["working-backwards"], None, None
    db.commit()
    return start_attempt(db, child, junior_paper, "practice", [1, 2])


def _help(client, a, kind, n=1, answer=""):
    return client.post(f"/attempts/{a.id}/help", data={"q": str(n), "kind": kind, "answer": answer})


def _good_solution(paper):
    return ReferenceSolution(steps=["Undo the last step first.", "Then halve it."],
                             final_answer=_q(paper, 1).problem.answer)


def test_hint_one_names_technique():
    p = Problem(transcription="x", answer="1", tags=["working-backwards"])
    h = hint_one(p)
    assert h.startswith("This one smells like working backwards! 🕵️") and "Start from the end" in h


def test_hint_one_no_tags():
    assert hint_one(Problem(transcription="x", answer="1", tags=[])) == "Read it again slowly and draw a picture!"


def test_first_step():
    assert first_step("1. Undo the last step.\n2. Then halve.") == "Undo the last step."
    assert first_step("") == ""


def test_solution_state():
    assert solution_state(Problem(verified=True)) == "ready"
    assert solution_state(Problem(verified=False)) == "failed"
    assert solution_state(Problem(verified=None)) == "missing"


def test_hint_records_use(child_client, db, att):
    r = _help(child_client, att, "hint")
    assert r.status_code == 200 and "working backwards" in r.text
    db.expire_all()
    assert response_for(db.get(Attempt, att.id), 1).hints_used == 1


def test_hint2_waits_then_shows_first_step(child_client, db, fake_ai, att, junior_paper):
    fake_ai.add(ReferenceSolution, _good_solution(junior_paper))
    r = _help(child_client, att, "hint2")           # starts the solve (runs as a background task)
    assert "let me think" in r.text and "hx-get" in r.text
    r = child_client.get(f"/attempts/{att.id}/help", params={"q": 1, "kind": "hint2"})
    assert "Undo the last step first." in r.text and "Then halve it." not in r.text
    db.expire_all()
    assert response_for(db.get(Attempt, att.id), 1).hints_used == 2


def test_solution_ready_shows_steps_and_locks(child_client, db, att, junior_paper):
    p = _q(junior_paper, 1).problem
    p.reference_solution, p.verified = "1. Undo the last step first.\n2. Then halve it.", True
    db.commit()
    r = _help(child_client, att, "solution")
    assert "Then halve it." in r.text and f"The answer is {p.answer}." in r.text
    assert r.headers.get("HX-Trigger") == "bb-locked"
    db.expire_all()
    resp = response_for(db.get(Attempt, att.id), 1)
    assert resp.solution_seen and resp.gave_up and resp.locked


def test_solution_after_right_answer_is_not_a_give_up(child_client, db, att, junior_paper):
    p = _q(junior_paper, 1).problem
    p.reference_solution, p.verified = "1. Step.", True
    db.commit()
    _help(child_client, att, "solution", answer=p.answer)       # typed the right answer, unchecked
    db.expire_all()
    resp = response_for(db.get(Attempt, att.id), 1)
    assert resp.correct_first is True and not resp.gave_up and resp.solution_seen


def test_solution_missing_starts_one_solve(db, settings, session_factory, fake_ai, app, att, junior_paper):
    calls = []
    app.state.ai = fake_ai
    fake_ai.add(ReferenceSolution, _good_solution(junior_paper))
    pid = _q(junior_paper, 1).problem_id
    run = []
    assert request_solve(app, pid, run.append) is True
    assert request_solve(app, pid, run.append) is False          # already thinking: no second job
    assert len(run) == 1
    run[0]()
    assert fake_ai.calls(ReferenceSolution) == 1 and pid not in helper._inflight
    db.expire_all()
    assert db.get(Problem, pid).verified is True


def test_solution_unverifiable_gives_answer_only(child_client, db, att, junior_paper):
    p = _q(junior_paper, 1).problem
    p.verified = False
    db.commit()
    r = _help(child_client, att, "solution")
    assert "couldn't work out the steps" in r.text.replace("&#39;", "'") and f"The answer is {p.answer}." in r.text


def test_ai_error_foggy(child_client, db, fake_ai, att):
    fake_ai.add(ReferenceSolution, AIError("down"))
    _help(child_client, att, "hint2")
    r = child_client.get(f"/attempts/{att.id}/help", params={"q": 1, "kind": "hint2"})
    assert "My brain's foggy — try again in a bit." in r.text.replace("&#39;", "'") and "hx-get" not in r.text


def test_help_forbidden_in_exam(child_client, db, child, junior_paper):
    a = start_attempt(db, child, junior_paper, "contest", [1])
    for kind in ("hint", "hint2", "solution"):
        assert _help(child_client, a, kind).status_code == 403
    db.expire_all()
    r = response_for(db.get(Attempt, a.id), 1)
    assert not r.hints_used and not r.solution_seen


def test_help_bad_kind(child_client, att):
    assert _help(child_client, att, "answer-please").status_code == 400
