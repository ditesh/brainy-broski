"""Fixes from the final review of practice/exam/burrow."""
from app import helper
from app.ai.schemas import ReferenceSolution
from app.models import AnswerType, Attempt, Problem
from app.practice.service import check_answer, give_up, misses, response_for, save_answer, start_attempt, submit


def _q(paper, n):
    return next(q for q in paper.questions if q.number == n)


MCQ = "Pick one.\n\n(A) 1\n(B) 2\n(C) 3"


def _mcq(db, paper):
    p = _q(paper, 1).problem
    p.answer_type, p.transcription, p.answer = AnswerType.mcq, MCQ, "B"
    db.commit()


# 1 (critical): solving works after a restart, before anything else has set app.state.ai
def test_solve_works_without_ai_already_on_app(app, db, fake_ai, junior_paper, monkeypatch):
    pid = _q(junior_paper, 1).problem_id
    fake_ai.add(ReferenceSolution, ReferenceSolution(steps=["a"], final_answer=_q(junior_paper, 1).problem.answer))
    del app.state.ai
    monkeypatch.setattr("app.helper.ensure_ai", lambda a: fake_ai)
    helper._inflight.clear(); helper._errors.clear()
    run = []
    helper.request_solve(app, pid, run.append)
    run[0]()
    db.expire_all()
    assert db.get(Problem, pid).verified is True and pid not in helper._errors


# 2: giving up on a tapped-but-unchecked MCQ option checks the tapped option first
def test_give_up_checks_a_tapped_option(db, child, junior_paper):
    _mcq(db, junior_paper)
    a = start_attempt(db, child, junior_paper, "practice", [1])
    save_answer(db, a, 1, "B")
    give_up(db, a, 1)
    r = response_for(a, 1)
    assert r.correct_first is True and not r.gave_up


def test_give_up_on_a_wrong_tapped_option_is_a_miss(db, child, junior_paper):
    _mcq(db, junior_paper)
    a = start_attempt(db, child, junior_paper, "practice", [1])
    save_answer(db, a, 1, "A")
    give_up(db, a, 1)
    submit(db, a)
    r = response_for(a, 1)
    assert r.correct_first is False and r.gave_up and r.first_answer == "A"


# 3: seeing the solution after two wrong tries keeps the usual after-hand-in help
def test_solution_after_two_wrong_tries_keeps_diagnosis(child_client, db, child, junior_paper):
    p = _q(junior_paper, 1).problem
    p.reference_solution, p.verified = "1. Step.", True
    db.commit()
    a = start_attempt(db, child, junior_paper, "practice", [1])
    check_answer(db, a, 1, "99999")
    check_answer(db, a, 1, "88888")
    child_client.post(f"/attempts/{a.id}/help", data={"q": "1", "kind": "solution"})
    db.expire_all()
    a = db.get(Attempt, a.id)
    submit(db, a)
    r = response_for(a, 1)
    assert r.solution_seen and not r.helped_out and r in misses(a)


# 4: an empty Check stays on the question with a message
def test_empty_check_stays_on_question(child_client, db, child, junior_paper):
    a = start_attempt(db, child, junior_paper, "practice", [1, 2])
    r = child_client.post(f"/attempts/{a.id}/check", data={"q": "1", "answer": " "}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/attempts/{a.id}?q=1&v=empty"
    assert "Type an answer first" in child_client.get(r.headers["location"]).text


# 5: an unchecked MCQ in practice can still move on
def test_mcq_practice_has_next(child_client, db, child, junior_paper):
    _mcq(db, junior_paper)
    a = start_attempt(db, child, junior_paper, "practice", [1, 2])
    html = child_client.get(f"/attempts/{a.id}?q=1").text
    assert f'<a class="button" href="/attempts/{a.id}?q=2">Next →</a>' in html


# minor→important: a wrong option can't be tapped again on the second try
def test_wrong_option_disabled_on_second_try(child_client, db, child, junior_paper):
    _mcq(db, junior_paper)
    a = start_attempt(db, child, junior_paper, "practice", [1])
    check_answer(db, a, 1, "A")
    html = child_client.get(f"/attempts/{a.id}?q=1").text
    wrong = next(b for b in html.split("<button") if 'value="A"' in b and "mcq-choice" in b)
    assert "disabled" in wrong.split(">")[0]


# minor→important: Enter in a practice text box checks the answer
def test_enter_checks_in_practice(child_client, db, child, junior_paper):
    a = start_attempt(db, child, junior_paper, "practice", [1, 2])
    html = child_client.get(f"/attempts/{a.id}?q=2").text
    form = html[html.index('id="answer-form"'):]
    first_button = form[form.index("<button"):].split(">")[0]
    assert 'formaction="/attempts/' in first_button and "/check" in first_button
