"""Practice checks as you go: one retry, then the answer; give up; locked answers; marks at hand-in."""
import pytest

from app.models import Label
from app.practice.service import (check_answer, give_up, misses, response_for, save_answer, start_attempt,
                                  start_redo, submit)


def _q(paper, n):
    return next(q for q in paper.questions if q.number == n)


def _right(paper, n):
    return _q(paper, n).problem.answer


@pytest.fixture
def att(db, child, junior_paper):
    return start_attempt(db, child, junior_paper, "practice", [1, 2, 3])


def test_check_right_locks(db, att, junior_paper):
    assert check_answer(db, att, 1, _right(junior_paper, 1)) == "right"
    r = response_for(att, 1)
    assert r.correct_first is True and r.locked and r.checked_at is not None
    with pytest.raises(ValueError):
        save_answer(db, att, 1, "7")


def test_check_wrong_then_right_second(db, att, junior_paper):
    assert check_answer(db, att, 1, "99999") == "wrong"
    r = response_for(att, 1)
    assert r.correct_first is False and not r.locked
    assert check_answer(db, att, 1, _right(junior_paper, 1)) == "right_second"
    assert r.correct_retry is True and r.retry_answer == _right(junior_paper, 1)
    assert r.first_answer == "99999" and r.label == Label.careless_self_corrected and r.locked


def test_check_wrong_twice(db, att):
    check_answer(db, att, 1, "99999")
    assert check_answer(db, att, 1, "88888") == "wrong_second"
    r = response_for(att, 1)
    assert r.correct_retry is False and r.locked
    with pytest.raises(ValueError):
        check_answer(db, att, 1, "77777")


def test_check_refused_in_exam(db, child, junior_paper):
    a = start_attempt(db, child, junior_paper, "contest", [1])
    with pytest.raises(ValueError):
        check_answer(db, a, 1, "5")
    with pytest.raises(ValueError):
        give_up(db, a, 1)


def test_check_blank_refused(db, att):
    with pytest.raises(ValueError):
        check_answer(db, att, 1, "  ")


def test_give_up_blank_is_a_miss_without_penalty(db, att, junior_paper):
    _q(junior_paper, 1).penalty = 1
    db.commit()
    give_up(db, att, 1)
    r = response_for(att, 1)
    assert r.gave_up and r.locked and r.helped_out
    submit(db, att)
    assert r.correct_first is False and att.score == 0
    assert r not in misses(att)
    redo = start_redo(db, att)
    assert redo.question_numbers == [1]


def test_give_up_checks_typed_answer_first(db, att, junior_paper):
    give_up(db, att, 2, _right(junior_paper, 2))
    r = response_for(att, 2)
    assert r.correct_first is True and not r.gave_up and r.locked


def test_give_up_with_wrong_typed_answer_is_not_blank(db, att):
    give_up(db, att, 2, "99999")
    r = response_for(att, 2)
    assert r.correct_first is False and r.first_answer == "99999" and r.gave_up


def test_submit_keeps_checked_marks_and_marks_unchecked(db, att, junior_paper):
    check_answer(db, att, 1, "99999")
    check_answer(db, att, 1, _right(junior_paper, 1))     # right on the second go: still a first-answer miss
    save_answer(db, att, 2, _right(junior_paper, 2))      # never checked
    submit(db, att)
    r1, r2, r3 = (response_for(att, n) for n in (1, 2, 3))
    assert r1.correct_first is False and r1.correct_retry is True
    assert r2.correct_first is True and r3.correct_first is None
    assert att.score == _q(junior_paper, 2).points


def test_locked_answer_cannot_be_saved_via_route(child_client, db, att, junior_paper):
    check_answer(db, att, 1, _right(junior_paper, 1))
    r = child_client.post(f"/attempts/{att.id}/answer", data={"q": "1", "answer": "7", "go": "1"},
                          follow_redirects=False)
    assert r.status_code == 400
    db.expire_all()
    assert response_for(att, 1).first_answer == _right(junior_paper, 1)


def test_timer_on_stored(db, child, junior_paper):
    assert start_attempt(db, child, junior_paper, "practice", [1], timer_on=True).timer_on is True
    assert not start_attempt(db, child, junior_paper, "practice", [1]).timer_on
