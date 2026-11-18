"""Retaking papers: done-marks on the paper list, try numbers, redo-my-misses, no double counting."""
from datetime import timedelta

import pytest
from freezegun import freeze_time

from app.models import Label
from app.practice.service import paper_status, save_answer, start_attempt, start_redo, submit
from app.progress import paper_history, technique_table


def _take(db, child, paper, answers: dict[int, str], numbers=None):
    a = start_attempt(db, child, paper, "practice", numbers)
    for n, v in answers.items():
        save_answer(db, a, n, v)
    submit(db, a)
    return a


# ---- redo my misses ----

def test_redo_contains_only_missed_questions(db, junior_paper, child):
    a = _take(db, child, junior_paper, {1: "18", 2: "99", 3: "0"})
    redo = start_redo(db, a)
    assert redo.question_numbers == [2, 3]
    assert redo.redo_of_id == a.id and redo.mode == "practice"


def test_redo_includes_self_corrected_misses(db, junior_paper, child):
    from app.practice.service import submit_retry
    a = _take(db, child, junior_paper, {1: "0", 2: "99"})
    r1 = next(r for r in a.responses if r.paper_question.number == 1)
    submit_retry(db, r1, "18")
    assert start_redo(db, a).question_numbers == [1, 2]


def test_redo_with_no_misses_refused(db, junior_paper, child):
    a = _take(db, child, junior_paper, {1: "18"})
    with pytest.raises(ValueError):
        start_redo(db, a)


def test_redo_reuses_open_redo(db, junior_paper, child):
    a = _take(db, child, junior_paper, {2: "99"})
    assert start_redo(db, a).id == start_redo(db, a).id


def test_redo_button_shown_after_retries_done(child_client, db, junior_paper, child):
    from app.practice.service import submit_retry
    a = _take(db, child, junior_paper, {2: "99"})
    html = child_client.get(f"/attempts/{a.id}/results").text
    assert "Redo my misses" not in html  # still has a second try to use
    submit_retry(db, next(r for r in a.responses if r.paper_question.number == 2), "98")
    assert "Redo my misses" in child_client.get(f"/attempts/{a.id}/results").text


def test_redo_route_starts_attempt(child_client, db, junior_paper, child):
    a = _take(db, child, junior_paper, {2: "99"})
    resp = child_client.post(f"/attempts/{a.id}/redo", follow_redirects=False)
    assert resp.status_code == 303
    from app.models import Attempt
    redo = db.query(Attempt).filter_by(redo_of_id=a.id).one()
    assert resp.headers["location"] == f"/attempts/{redo.id}?q=2"


def test_redo_route_other_child_404(child2_client, db, junior_paper, child):
    a = _take(db, child, junior_paper, {2: "99"})
    assert child2_client.post(f"/attempts/{a.id}/redo").status_code == 404


# ---- paper list ----

def test_paper_status_last_whole_paper_attempt(db, junior_paper, child):
    with freeze_time("2026-11-01"):
        _take(db, child, junior_paper, {1: "18"})
    with freeze_time("2026-11-10"):
        a2 = _take(db, child, junior_paper, {1: "18", 2: "99"})
    with freeze_time("2026-11-15"):
        start_redo(db, a2)  # redos don't count as doing the paper
    with freeze_time("2026-11-18"):
        st = paper_status(db, child)[junior_paper.id]
    assert st["days_ago"] == 8 and st["score"] == a2.score and st["tries"] == 2


def test_paper_list_shows_done_and_recent_warning(child_client, db, junior_paper, child):
    _take(db, child, junior_paper, {1: "18"})
    html = child_client.get("/practice?contest=IMONST&level=Junior").text
    assert "Done today" in html
    assert "you might remember some answers" in html


def test_paper_list_no_warning_after_30_days(child_client, db, junior_paper, child):
    from app.models import utcnow
    a = _take(db, child, junior_paper, {1: "18"})
    a.started_at = a.submitted_at = utcnow() - timedelta(days=40)
    db.commit()
    html = child_client.get("/practice?contest=IMONST&level=Junior").text
    assert "Done " + a.submitted_at.strftime("%d %b") in html
    assert "you might remember some answers" not in html


# ---- progress ----

def test_history_labels_tries_and_redos(db, junior_paper, child):
    with freeze_time("2026-11-01"):
        a1 = _take(db, child, junior_paper, {2: "99"})
    with freeze_time("2026-11-05"):
        _take(db, child, junior_paper, {1: "18"})
    with freeze_time("2026-11-08"):
        redo = start_redo(db, a1)
        submit(db, redo)
    kinds = [h["kind"] for h in paper_history(db, child)]
    assert kinds == ["Redo of misses", "2nd try", ""]


def test_technique_table_counts_each_problem_once(db, junior_paper, child):
    a1 = _take(db, child, junior_paper, {2: "99"})
    _take(db, child, junior_paper, {2: "97"})
    submit(db, start_redo(db, a1))
    tags = set(next(r for r in a1.responses if r.paper_question.number == 2).paper_question.problem.tags)
    rows = {r["tag"]: r for r in technique_table(db, child)}
    for t in tags:
        assert rows[t]["misses"] == 1 and rows[t]["attempts"] == 1
        assert not rows[t]["flagged"]
