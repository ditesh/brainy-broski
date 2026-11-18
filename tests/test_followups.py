from datetime import timedelta

import pytest

from app.followups import answer_followup, pick_followups
from app.models import DiagnosisStatus, FollowupResponse, Label, utcnow
from app.practice.service import save_answer, start_attempt, submit, submit_retry
from tests.conftest import get_pq

TAG = "casework"  # synthetic tags: Junior Q2 (= Primary Q7) is casework; so are Junior 7/11/15/19, Primary 3/11/15/19


@pytest.fixture
def response(db, papers, child):
    a = start_attempt(db, child, papers["Junior"], "practice", [2])
    save_answer(db, a, 2, "5")
    submit(db, a)
    r = a.responses[0]
    submit_retry(db, r, "6")
    p = r.paper_question.problem
    p.verified, p.reference_solution = True, "1. Count the cases."
    r.label, r.diagnosis_status = Label.technique, DiagnosisStatus.done
    r.diagnosis = {"label": "technique", "technique_tag": TAG, "hint": "h", "explanation": "e", "wrong_step": None}
    db.commit()
    return r


def test_excludes_same_problem_and_duplicates(db, child, papers, response):
    picks = pick_followups(db, child, response, TAG, n=10)
    assert response.paper_question.problem_id not in {p.problem_id for p in picks}
    assert get_pq(db, papers["Primary"], 7).id not in {p.id for p in picks}
    assert len({p.problem_id for p in picks}) == len(picks)


def test_prefers_same_category(db, child, response):
    picks = pick_followups(db, child, response, TAG, n=2)
    assert [p.paper.category for p in picks] == ["Junior", "Junior"]


def test_stable_order(db, child, response):
    assert pick_followups(db, child, response, TAG) == pick_followups(db, child, response, TAG)


def test_excludes_recently_answered(db, child, papers, response):
    a = start_attempt(db, child, papers["Junior"], "practice", [11, 15])
    save_answer(db, a, 11, "1")
    save_answer(db, a, 15, "1")
    picks = pick_followups(db, child, response, TAG, n=10)
    assert {p.number for p in picks if p.paper.category == "Junior"} == {7, 19}


def test_old_answers_not_excluded(db, child, papers, response):
    a = start_attempt(db, child, papers["Junior"], "practice", [11])
    save_answer(db, a, 11, "1")
    submit(db, a)  # handed in: questions in unfinished papers are never offered
    a.started_at = utcnow() - timedelta(days=40)
    db.commit()
    assert 11 in {p.number for p in pick_followups(db, child, response, TAG, n=10) if p.paper.category == "Junior"}


def test_unpublished_excluded(db, child, papers, response):
    papers["Primary"].published = False
    db.commit()
    assert all(p.paper.category == "Junior" for p in pick_followups(db, child, response, TAG, n=10))


def test_answer_followup_records(db, child, papers, response):
    pq = get_pq(db, papers["Junior"], 11)  # answer 133
    f = answer_followup(db, child, response, pq, " 133 ")
    assert f.correct and db.query(FollowupResponse).count() == 1


def test_card_shows_followups(child_client, response):
    html = child_client.get(f"/responses/{response.id}/feedback").text
    assert html.count('class="followup') == 2 and "Try one like it" in html


def test_followup_wrong_reveals_answer(child_client, db, papers, response):
    pq = get_pq(db, papers["Junior"], 11)
    html = child_client.post(f"/responses/{response.id}/followups/{pq.id}", data={"answer": "1"}).text
    assert "Not quite" in html and "133" in html


def test_followup_correct(child_client, db, papers, response):
    pq = get_pq(db, papers["Junior"], 11)
    assert "Correct!" in child_client.post(f"/responses/{response.id}/followups/{pq.id}", data={"answer": "133"}).text


def test_answered_followup_stays_on_card(child_client, db, papers, response):
    pq = get_pq(db, papers["Junior"], 11)
    child_client.post(f"/responses/{response.id}/followups/{pq.id}", data={"answer": "133"})
    html = child_client.get(f"/responses/{response.id}/feedback").text
    assert "Correct!" in html and html.count('class="followup') == 2


def test_none_available_message(child_client, db, papers, response):
    for p in papers.values():
        for q in p.questions:
            if q.problem_id != response.paper_question.problem_id:
                q.problem.tags = ["logic"]
    db.commit()
    html = child_client.get(f"/responses/{response.id}/feedback").text
    assert "No more practice questions for this technique yet." in html


def test_other_child_cannot_answer(child2_client, db, papers, response):
    pq = get_pq(db, papers["Junior"], 11)
    assert child2_client.post(f"/responses/{response.id}/followups/{pq.id}", data={"answer": "1"}).status_code == 404
