from datetime import timedelta

import pytest

from app.followups import answer_followup
from app.models import DiagnosisStatus, Label, utcnow
from app.practice.service import save_answer, start_attempt, submit
from app.progress import (effective_label, miss_breakdown, miss_breakdown_by_week, paper_history,
                          technique_table)
from tests.conftest import get_pq


def do_paper(db, user, paper, answers: dict[int, str], labels: dict[int, Label], days_ago=0):
    a = start_attempt(db, user, paper, "practice", sorted(answers))
    for n, v in answers.items():
        save_answer(db, a, n, v)
    submit(db, a)
    a.started_at = a.submitted_at = utcnow() - timedelta(days=days_ago)
    for r in a.responses:
        n = r.paper_question.number
        if n in labels:
            r.label, r.diagnosis_status = labels[n], DiagnosisStatus.done
    db.commit()
    return a


@pytest.fixture
def history(db, child, papers):
    j = papers["Junior"]
    # synthetic tags: Junior Q7, Q11 casework; Q6, Q1 areas; Q8 parity
    a1 = do_paper(db, child, j, {6: "1", 7: "1", 1: "18"}, {6: Label.careless, 7: Label.technique}, days_ago=20)
    a2 = do_paper(db, child, j, {11: "1", 8: "1"}, {11: Label.technique, 8: Label.unsure}, days_ago=2)
    return a1, a2


def test_effective_label_prefers_override(db, history):
    r = next(x for x in history[0].responses if x.paper_question.number == 6)
    r.parent_override = Label.technique
    assert effective_label(r) == Label.technique


def test_breakdown(db, child, history):
    assert miss_breakdown(db, child, None) == {Label.careless: 1, Label.technique: 2, Label.unsure: 1}


def test_override_changes_breakdown(db, child, history):
    r = next(x for x in history[1].responses if x.paper_question.number == 11)
    r.parent_override = Label.careless
    db.commit()
    assert miss_breakdown(db, child, None)[Label.careless] == 2


def test_breakdown_since(db, child, history):
    assert miss_breakdown(db, child, (utcnow() - timedelta(days=7)).date()) == {Label.technique: 1, Label.unsure: 1}


def test_by_week_has_8_buckets(db, child, history):
    weeks = miss_breakdown_by_week(db, child, weeks=8)
    assert len(weeks) == 8 and sum(sum(d.values()) for _, d in weeks) == 4


def test_flagged_after_two_recent_misses(db, child, papers, history):
    rows = {r["tag"]: r for r in technique_table(db, child)}
    assert rows["casework"]["misses"] == 2 and rows["casework"]["recent_misses"] == 2
    assert rows["casework"]["flagged"] and not rows["parity"]["flagged"]


def test_followups_count_toward_technique_attempts(db, child, papers, history):
    before = {r["tag"]: r for r in technique_table(db, child)}["casework"]["attempts"]
    r = next(x for x in history[1].responses if x.paper_question.number == 11)
    answer_followup(db, child, r, get_pq(db, papers["Junior"], 15), "1")
    after = {r["tag"]: r for r in technique_table(db, child)}["casework"]
    assert after["attempts"] == before + 1 and after["misses"] == 3


def test_paper_history(db, child, history):
    rows = paper_history(db, child)
    assert [r["score"] for r in rows] == [0, 1] and rows[0]["title"] == "IMONST 2020 Junior"


def test_progress_page_child(child_client, history):
    html = child_client.get("/progress").text
    assert "<svg" in html and "Counting by cases" in html and "IMONST 2020 Junior" in html


def test_child_sees_only_own_progress(child_client, child2, db, papers, history):
    do_paper(db, child2, papers["Junior"], {9: "1"}, {9: Label.careless})
    html = child_client.get(f"/progress?user={child2.id}").text
    assert "Junior Q9" not in html


def test_parent_sees_child_progress(parent_client, history):
    html = parent_client.get("/progress").text
    assert "Kid" in html and "Counting by cases" in html


def test_parent_override_route(parent_client, db, history):
    r = next(x for x in history[0].responses if x.paper_question.number == 6)
    parent_client.post(f"/parent/responses/{r.id}/override", data={"label": "technique"})
    db.refresh(r)
    assert r.parent_override == Label.technique


def test_child_cannot_override(child_client, history):
    r = history[0].responses[0]
    assert child_client.post(f"/parent/responses/{r.id}/override", data={"label": "careless"}).status_code == 403
