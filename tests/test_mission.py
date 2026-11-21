"""Today's mission on the child's home page, handed over by a buddy who talks."""
import json
import re

from app.models import Attempt
from app.pets.creatures import CREATURES
from app.practice.service import save_answer, start_attempt, submit
from app.mission import mission_for


def _q(paper, n):
    return next(q for q in paper.questions if q.number == n)


def _problems(db, m):
    from app.models import Paper
    paper = db.get(Paper, m.paper_id)
    return {_q(paper, n).problem_id for n in m.numbers}


def _tag(db, paper, tags: dict[int, str]):
    for q in paper.questions:
        q.problem.tags = [tags.get(q.number, "logic")]
    db.commit()


def _do(db, child, paper, answers: dict[int, bool]):
    a = start_attempt(db, child, paper, "practice", sorted(answers))
    for n, right in answers.items():
        save_answer(db, a, n, _q(paper, n).problem.answer if right else "99999")
    submit(db, a)
    return a


def test_no_mission_without_papers(db, child):
    assert mission_for(db, child) is None


def test_finish_what_you_started_comes_first(db, child, junior_paper):
    a = start_attempt(db, child, junior_paper, "practice", [1, 2, 3])
    save_answer(db, a, 1, "5")
    m = mission_for(db, child)
    assert m.kind == "continue" and m.attempt_id == a.id and "2 questions left" in m.detail


def test_grows_the_pet_closest_to_its_next_stage(db, child, papers, junior_paper):
    _tag(db, papers["Primary"], {})
    _tag(db, junior_paper, {1: "parity", 2: "parity", 3: "parity", 4: "parity", 5: "algebra", 6: "algebra"})
    _do(db, child, junior_paper, {1: True})          # parity 1 point: 1 away from hatching
    m = mission_for(db, child)
    assert m.kind == "grow" and m.tag == "parity"
    # the unanswered parity problems, max 3 (the Primary paper reuses some of Junior's problems)
    assert _problems(db, m) == {_q(junior_paper, n).problem_id for n in (2, 3, 4)}
    assert CREATURES["parity"].name not in m.title                    # still an egg: name kept secret
    assert "1 away from hatching" in m.detail


def test_names_a_hatched_pet(db, child, papers, junior_paper):
    _tag(db, papers["Primary"], {})
    parity = {n: "parity" for n in (6, 11, 12, 13, 14, 15, 16)}
    _tag(db, junior_paper, parity)
    _do(db, child, junior_paper, {6: True, 11: True, 12: True, 13: True, 14: True})   # 2 + 4×3 = 14 points
    m = mission_for(db, child)
    assert m.tag == "parity" and CREATURES["parity"].name in m.title and m.numbers == [15, 16]
    assert "1 away from growing up" in m.detail


def test_skips_questions_already_answered(db, child, papers, junior_paper):
    _tag(db, papers["Primary"], {})
    _tag(db, junior_paper, {1: "parity", 2: "parity"})
    _do(db, child, junior_paper, {1: True, 2: False})   # parity: none left unanswered
    m = mission_for(db, child)
    assert m.tag != "parity"
    assert not _problems(db, m) & {_q(junior_paper, n).problem_id for n in (1, 2)}


def test_redo_misses_when_everything_answered(db, child, papers, junior_paper):
    papers["Primary"].published = False
    a = _do(db, child, junior_paper, {q.number: q.number != 4 for q in junior_paper.questions})
    m = mission_for(db, child)
    assert m.kind == "redo" and m.attempt_id == a.id


def test_nothing_left_at_all(db, child, papers, junior_paper):
    papers["Primary"].published = False
    _do(db, child, junior_paper, {q.number: True for q in junior_paper.questions})
    assert mission_for(db, child) is None


# ---- web ----

def test_home_shows_mission_with_start(child_client, db, child, papers, junior_paper):
    _tag(db, papers["Primary"], {})
    _tag(db, junior_paper, {1: "parity", 2: "parity"})
    html = child_client.get("/practice").text
    assert 'class="mission' in html and 'action="/mission/start"' in html


def test_start_mission_makes_an_attempt(child_client, db, child, papers, junior_paper):
    _tag(db, papers["Primary"], {})
    _tag(db, junior_paper, {1: "parity", 2: "parity", 3: "parity", 4: "parity"})
    r = child_client.post("/mission/start", data={"paper_id": junior_paper.id, "numbers": "1,2,3"},
                          follow_redirects=False)
    a = db.query(Attempt).one()
    assert r.status_code == 303 and r.headers["location"] == f"/attempts/{a.id}?q=1"
    assert a.question_numbers == [1, 2, 3] and a.mode == "practice"


def test_start_mission_rejects_bad_input(child_client, db, junior_paper):
    assert child_client.post("/mission/start", data={"paper_id": junior_paper.id, "numbers": "1,99"}).status_code == 400
    assert child_client.post("/mission/start", data={"paper_id": junior_paper.id, "numbers": "x"}).status_code == 400
    assert child_client.post("/mission/start", data={"paper_id": 999, "numbers": "1"}).status_code == 404
    assert db.query(Attempt).count() == 0


def test_start_mission_rejects_unpublished(child_client, db, imported_paper):
    r = child_client.post("/mission/start", data={"paper_id": imported_paper.id, "numbers": "1"})
    assert r.status_code == 404


def test_buddy_talks(child_client, db, child, papers, junior_paper, monkeypatch):
    _tag(db, papers["Primary"], {})
    _tag(db, junior_paper, {6: "parity", 7: "parity"})
    _do(db, child, junior_paper, {6: True})          # hatches Evenix, who becomes the buddy
    child_client.post("/goal", data={"target": "5"})
    html = child_client.get("/practice").text
    lines = json.loads(re.search(r"data-lines='([^']*)'", html).group(1).replace("&#34;", '"'))
    assert any("4 to go" in line for line in lines)                  # goal 5, 1 done
    assert any(CREATURES["parity"].catchphrase in line for line in lines)
    assert 'class="speech"' in html


def test_greeting_depends_on_time(db, child, papers, junior_paper):
    from datetime import datetime
    from app.mission import buddy_lines
    from app.goals import GoalStatus
    morning = buddy_lines(child, None, GoalStatus(None, 0, False, 0, None), None, datetime(2026, 11, 20, 8))
    evening = buddy_lines(child, None, GoalStatus(None, 0, False, 0, None), None, datetime(2026, 11, 20, 20))
    assert "morning" in morning[0].lower() and "evening" in evening[0].lower()


def test_parents_get_no_mission(parent_client, db, junior_paper):
    assert 'class="mission' not in parent_client.get("/practice").text
    assert parent_client.post("/mission/start", data={"paper_id": junior_paper.id, "numbers": "1"}).status_code == 403


def test_mission_sticks_to_the_level_on_screen(child_client, db, child, papers, junior_paper):
    _tag(db, papers["Primary"], {})
    _tag(db, junior_paper, {})
    html = child_client.get("/practice?contest=IMONST1&level=Junior").text
    hero = html[html.index("mission-hero"):html.index("goal-card")]
    assert junior_paper.title in hero and papers["Primary"].title not in hero
