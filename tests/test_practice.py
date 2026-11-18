from datetime import timedelta

import pytest

from app.models import Label, Response
from app.practice.service import misses, save_answer, start_attempt, submit, submit_retry
from tests.conftest import get_pq


def resp(attempt, n):
    return next(r for r in attempt.responses if r.paper_question.number == n)


@pytest.fixture
def attempt(db, junior_paper, child):
    return start_attempt(db, child, junior_paper, "practice", None)


def test_score_weighted_by_points(db, junior_paper, child, attempt):
    save_answer(db, attempt, 1, "18")
    save_answer(db, attempt, 16, "148")
    save_answer(db, attempt, 2, "99")
    submit(db, attempt)
    assert (attempt.score, attempt.max_score) == (1 + 4, 50)
    assert attempt.submitted_at is not None


def test_subset_max_score(db, junior_paper, child):
    a = start_attempt(db, child, junior_paper, "practice", [11, 12])
    assert len(a.responses) == 2
    submit(db, a)
    assert a.max_score == 6 and a.score == 0


def test_subset_rejects_unknown_numbers(db, junior_paper, child):
    with pytest.raises(ValueError):
        start_attempt(db, child, junior_paper, "practice", [99])


def test_blank_not_a_miss(db, attempt):
    save_answer(db, attempt, 2, "1")
    submit(db, attempt)
    assert resp(attempt, 3).correct_first is None
    assert resp(attempt, 3) not in misses(attempt) and resp(attempt, 2) in misses(attempt)


def test_answer_forms_marked_like_a_human(db, attempt):
    save_answer(db, attempt, 1, " 018 ")
    submit(db, attempt)
    assert resp(attempt, 1).correct_first is True


def test_retry_correct_is_careless_self_corrected(db, attempt):
    save_answer(db, attempt, 1, "81")
    submit(db, attempt)
    r = submit_retry(db, resp(attempt, 1), "18")
    assert r.correct_retry is True and r.label == Label.careless_self_corrected
    assert r not in misses(attempt)


def test_retry_wrong_stays_a_miss(db, attempt):
    save_answer(db, attempt, 1, "81")
    submit(db, attempt)
    r = submit_retry(db, resp(attempt, 1), "17")
    assert r.correct_retry is False and r in misses(attempt) and r.label is None


def test_retry_only_once(db, attempt):
    save_answer(db, attempt, 1, "81")
    submit(db, attempt)
    submit_retry(db, resp(attempt, 1), "17")
    with pytest.raises(ValueError):
        submit_retry(db, resp(attempt, 1), "18")


def test_retry_not_allowed_on_correct_or_blank(db, attempt):
    save_answer(db, attempt, 1, "18")
    submit(db, attempt)
    with pytest.raises(ValueError):
        submit_retry(db, resp(attempt, 1), "18")
    with pytest.raises(ValueError):
        submit_retry(db, resp(attempt, 2), "21")


def test_cannot_answer_after_submit(db, attempt):
    submit(db, attempt)
    with pytest.raises(ValueError):
        save_answer(db, attempt, 1, "18")


# ---- web ----

def test_picker_defaults_to_junior_and_hides_unpublished(child_client, papers, db):
    papers["Primary"].published = False
    db.commit()
    html = child_client.get("/practice").text
    assert "IMONST 2020 Junior" in html and "IMONST 2020 Primary" not in html


def test_start_and_answer_flow(child_client, junior_paper, db):
    r = child_client.post("/practice/start", data={"paper_id": junior_paper.id, "mode": "practice", "part": ""},
                          follow_redirects=False)
    assert r.status_code == 303
    url = r.headers["location"]
    aid = int(url.split("/")[2].split("?")[0])
    page = child_client.get(url).text
    assert 'class="qimg"' in page and 'inputmode="numeric"' in page
    child_client.post(f"/attempts/{aid}/answer", data={"q": "1", "answer": "18", "go": "2"})
    assert 'value="18"' in child_client.get(f"/attempts/{aid}?q=1").text  # resume keeps answers
    r = child_client.post(f"/attempts/{aid}/submit", follow_redirects=False)
    assert r.headers["location"] == f"/attempts/{aid}/results"
    assert "1 / 50" in child_client.get(f"/attempts/{aid}/results").text


def test_start_part_only(child_client, junior_paper, db):
    r = child_client.post("/practice/start", data={"paper_id": junior_paper.id, "mode": "practice",
                                                   "part": "Part C"}, follow_redirects=False)
    assert "q=11" in r.headers["location"]


def test_child_cannot_see_results_before_submit(child_client, attempt):
    assert child_client.get(f"/attempts/{attempt.id}/results").status_code == 404


def test_child_cannot_open_other_users_attempt(child2_client, attempt):
    assert child2_client.get(f"/attempts/{attempt.id}").status_code == 404
    assert child2_client.post(f"/attempts/{attempt.id}/answer", data={"q": "1", "answer": "1"}).status_code == 404


def test_attempt_page_never_contains_official_answer(child_client, attempt, db):
    q = get_pq(db, attempt.paper, 14)
    q.problem.answer = "987654321"
    db.commit()
    assert "987654321" not in child_client.get(f"/attempts/{attempt.id}?q=14").text


def test_results_do_not_reveal_answer_before_feedback(child_client, attempt, db):
    q = get_pq(db, attempt.paper, 2)
    q.problem.answer = "987654321"
    db.commit()
    save_answer(db, attempt, 2, "5")
    submit(db, attempt)
    assert "987654321" not in child_client.get(f"/attempts/{attempt.id}/results").text


def test_retry_via_web(child_client, attempt, db):
    save_answer(db, attempt, 1, "81")
    submit(db, attempt)
    r = resp(attempt, 1)
    child_client.post(f"/responses/{r.id}/retry", data={"answer": "18"})
    db.refresh(r)
    assert r.label == Label.careless_self_corrected
    assert "fixed it" in child_client.get(f"/attempts/{attempt.id}/results").text


def test_contest_timer_expiry_autosubmits(child_client, db, junior_paper, child):
    a = start_attempt(db, child, junior_paper, "contest", None)
    a.started_at = a.started_at - timedelta(minutes=181)
    db.commit()
    r = child_client.get(f"/attempts/{a.id}", follow_redirects=False)
    assert r.headers["location"] == f"/attempts/{a.id}/results"
    db.refresh(a)
    assert a.submitted_at is not None


def test_in_progress_listed_for_resume(child_client, attempt):
    assert f"/attempts/{attempt.id}" in child_client.get("/practice").text


def test_parent_can_view_child_results(parent_client, attempt, db):
    submit(db, attempt)
    assert parent_client.get(f"/attempts/{attempt.id}/results").status_code == 200
