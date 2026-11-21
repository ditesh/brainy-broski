"""The question page in Practice (check as you go, give up, optional timer) and Exam (like the real thing)."""
from datetime import timedelta

from app.models import AnswerType, Attempt
from app.practice.service import check_answer, response_for, start_attempt, submit


def _q(paper, n):
    return next(q for q in paper.questions if q.number == n)


def _page(client, a, n=1):
    return client.get(f"/attempts/{a.id}?q={n}").text


def _post(client, a, what, n, answer=""):
    return client.post(f"/attempts/{a.id}/{what}", data={"q": str(n), "answer": answer}, follow_redirects=True)


def test_start_form_says_practice_and_exam(child_client, junior_paper):
    html = child_client.get("/practice").text
    assert "🧘 Practice" in html and "Exam (" in html and "Contest" not in html
    assert 'name="timer"' in html and "Use a timer" in html


def test_start_with_timer(child_client, db, junior_paper):
    child_client.post("/practice/start", data={"paper_id": junior_paper.id, "mode": "practice", "timer": "1"})
    assert db.query(Attempt).one().timer_on is True


def test_practice_page_has_check_and_give_up(child_client, db, child, junior_paper):
    a = start_attempt(db, child, junior_paper, "practice", [1, 2])
    html = _page(child_client, a)
    assert "Check ✓" in html and "I give up" in html


def test_exam_page_has_neither(child_client, db, child, junior_paper):
    a = start_attempt(db, child, junior_paper, "contest", [1, 2])
    html = _page(child_client, a)
    assert "Check ✓" not in html and "I give up" not in html


def test_check_right(child_client, db, child, junior_paper):
    a = start_attempt(db, child, junior_paper, "practice", [1, 2])
    html = _post(child_client, a, "check", 1, _q(junior_paper, 1).problem.answer).text
    assert "Correct! 🎉" in html and "Check ✓" not in html


def test_check_wrong_then_second_go(child_client, db, child, junior_paper):
    a = start_attempt(db, child, junior_paper, "practice", [1, 2])
    html = _post(child_client, a, "check", 1, "99999").text
    assert "Not quite, have another go!" in html and "Check ✓" in html
    html = _post(child_client, a, "check", 1, _q(junior_paper, 1).problem.answer).text
    assert "Got it on the second go! 💪" in html


def test_check_wrong_twice_reveals_answer(child_client, db, child, junior_paper):
    a = start_attempt(db, child, junior_paper, "practice", [1, 2])
    _post(child_client, a, "check", 1, "99999")
    html = _post(child_client, a, "check", 1, "88888").text
    assert f"The answer is {_q(junior_paper, 1).problem.answer}." in html


def test_give_up_reveals_answer(child_client, db, child, junior_paper):
    a = start_attempt(db, child, junior_paper, "practice", [1, 2])
    html = _post(child_client, a, "giveup", 1).text
    assert f"The answer is {_q(junior_paper, 1).problem.answer}." in html
    db.expire_all()
    assert response_for(db.get(Attempt, a.id), 1).gave_up


def test_exam_check_forbidden(child_client, db, child, junior_paper):
    a = start_attempt(db, child, junior_paper, "contest", [1, 2])
    assert child_client.post(f"/attempts/{a.id}/check", data={"q": "1", "answer": "5"}).status_code == 403
    assert child_client.post(f"/attempts/{a.id}/giveup", data={"q": "1"}).status_code == 403
    db.expire_all()
    assert response_for(db.get(Attempt, a.id), 1).first_answer is None


def test_check_after_hand_in_redirects(child_client, db, child, junior_paper):
    a = start_attempt(db, child, junior_paper, "practice", [1, 2])
    submit(db, a)
    r = child_client.post(f"/attempts/{a.id}/check", data={"q": "1", "answer": "5"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/attempts/{a.id}/results"
    db.expire_all()
    assert response_for(db.get(Attempt, a.id), 1).first_answer is None


def test_bad_check_input(child_client, db, child, junior_paper):
    a = start_attempt(db, child, junior_paper, "practice", [1, 2])
    assert child_client.post(f"/attempts/{a.id}/check", data={"q": "1", "answer": " "}).status_code == 400
    assert child_client.post(f"/attempts/{a.id}/check", data={"q": "9", "answer": "5"}).status_code == 400


def test_practice_timer_never_hands_in(child_client, db, child, junior_paper):
    a = start_attempt(db, child, junior_paper, "practice", [1, 2], timer_on=True)
    a.started_at -= timedelta(minutes=(junior_paper.duration_min or 60) + 5)
    db.commit()
    r = child_client.get(f"/attempts/{a.id}?q=1")
    assert r.status_code == 200 and "data-deadline" in r.text and "data-soft" in r.text
    child_client.post(f"/attempts/{a.id}/answer", data={"q": "1", "answer": "5", "go": "2"})
    db.expire_all()
    a = db.get(Attempt, a.id)
    assert a.submitted_at is None and response_for(a, 1).first_answer == "5"


def test_practice_without_timer_has_no_clock(child_client, db, child, junior_paper):
    a = start_attempt(db, child, junior_paper, "practice", [1])
    assert "data-deadline" not in _page(child_client, a)


def test_locked_question_shows_verdict_not_input(child_client, db, child, junior_paper):
    a = start_attempt(db, child, junior_paper, "practice", [1, 2])
    check_answer(db, a, 1, _q(junior_paper, 1).problem.answer)
    html = _page(child_client, a)
    assert "Correct! 🎉" in html and 'name="answer"' not in html and f'href="/attempts/{a.id}?q=2"' in html


MCQ = "Pick one.\n\n(A) 1\n(B) 2\n(C) 3"


def _mcq(db, paper):
    p = _q(paper, 1).problem
    p.answer_type, p.transcription, p.answer = AnswerType.mcq, MCQ, "B"
    db.commit()


def test_mcq_tap_in_practice_stays_on_question(child_client, db, child, junior_paper):
    _mcq(db, junior_paper)
    a = start_attempt(db, child, junior_paper, "practice", [1, 2])
    html = _page(child_client, a)
    assert 'name="go" value="1"' in html and "Check ✓" not in html       # nothing tapped yet
    child_client.post(f"/attempts/{a.id}/answer", data={"q": "1", "answer": "A", "go": "1"})
    assert "Check ✓" in _page(child_client, a)
    html = _post(child_client, a, "check", 1).text          # blank: checks the tapped option
    assert "Not quite, have another go!" in html and 'formaction="/attempts/' in html


def test_mcq_tap_in_exam_moves_on(child_client, db, child, junior_paper):
    _mcq(db, junior_paper)
    a = start_attempt(db, child, junior_paper, "contest", [1, 2])
    assert 'name="go" value="2"' in _page(child_client, a)
