"""After hand-in: where he needed help shows on results and progress; there's nothing for Claude to diagnose."""
from app.practice.service import check_answer, give_up, start_attempt, start_redo, submit


def _q(paper, n):
    return next(q for q in paper.questions if q.number == n)


def _done(db, child, paper, steps):
    a = start_attempt(db, child, paper, "practice", [1, 2, 3])
    steps(a)
    submit(db, a)
    return a


def test_results_mark_gave_up(child_client, db, child, junior_paper):
    a = _done(db, child, junior_paper, lambda a: give_up(db, a, 1))
    html = child_client.get(f"/attempts/{a.id}/results").text
    card = html[html.index('id="r'):]
    assert "Gave up" in card and f"/responses/" not in card.split("Question 2")[0]


def test_results_mark_saw_solution(child_client, db, child, junior_paper):
    def steps(a):
        give_up(db, a, 1)
        a.responses[0].solution_seen = True
        db.commit()
    a = _done(db, child, junior_paper, steps)
    assert "Saw the solution" in child_client.get(f"/attempts/{a.id}/results").text


def test_results_mark_used_hint(child_client, db, child, junior_paper):
    def steps(a):
        check_answer(db, a, 2, _q(junior_paper, 2).problem.answer)
        r = next(r for r in a.responses if r.paper_question.number == 2)
        r.hints_used = 1
        db.commit()
    a = _done(db, child, junior_paper, steps)
    assert "used a hint" in child_client.get(f"/attempts/{a.id}/results").text


def test_checked_in_practice_shows_on_results(child_client, db, child, junior_paper):
    a = _done(db, child, junior_paper, lambda a: (check_answer(db, a, 1, "99999"),
                                                  check_answer(db, a, 1, _q(junior_paper, 1).problem.answer)))
    html = child_client.get(f"/attempts/{a.id}/results").text
    assert "Fixed on second try" in html


def test_photo_refused_for_gave_up(child_client, db, child, junior_paper):
    a = _done(db, child, junior_paper, lambda a: give_up(db, a, 1, "99999"))
    r = next(r for r in a.responses if r.paper_question.number == 1)
    r.correct_retry = False   # even if a retry slipped through, a give-up never asks for a photo
    db.commit()
    assert child_client.get(f"/responses/{r.id}/photo").status_code == 400


def test_feedback_page_skips_gave_up(child_client, db, child, junior_paper):
    a = _done(db, child, junior_paper, lambda a: give_up(db, a, 1))
    html = child_client.get(f"/attempts/{a.id}/feedback").text
    assert "Question 1" not in html


def test_progress_lists_gave_up(parent_client, db, child, junior_paper):
    _done(db, child, junior_paper, lambda a: give_up(db, a, 1))
    html = parent_client.get(f"/progress?user={child.id}").text
    assert "Gave up" in html


def test_redo_includes_gave_up(db, child, junior_paper):
    a = _done(db, child, junior_paper, lambda a: give_up(db, a, 1))
    assert start_redo(db, a).question_numbers == [1]
