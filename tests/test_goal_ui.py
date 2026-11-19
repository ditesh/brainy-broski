"""Setting and seeing the weekly goal: practice home, Me page, parent Progress."""
from app.goals import set_goal
from app.daily import local_today
from app.practice.service import save_answer, start_attempt, submit


def _today(app):
    return local_today(app.state.settings.timezone)


def test_home_prompts_for_goal_without_blocking(child_client, junior_paper):
    html = child_client.get("/practice").text
    assert 'name="target"' in html and "Pick a challenge" in html and junior_paper.title in html


def test_set_goal_from_home(child_client):
    r = child_client.post("/goal", data={"target": "15"})
    assert r.status_code == 200 and "0 of 15 this week" in r.text


def test_goal_counts_answers(child_client, db, child, junior_paper):
    child_client.post("/goal", data={"target": "15"})
    a = start_attempt(db, child, junior_paper, "practice", [1, 2])
    save_answer(db, a, 1, "5")
    submit(db, a)
    assert "1 of 15 this week" in child_client.get("/practice").text


def test_bad_goal_rejected(child_client):
    for bad in ("0", "201", "abc", ""):
        r = child_client.post("/goal", data={"target": bad})
        assert r.status_code == 400 and "1 to 200" in r.text


def test_parent_cannot_set_goal(parent_client):
    assert parent_client.post("/goal", data={"target": "5"}).status_code == 403


def test_goal_form_on_me_page_returns_there(child_client):
    r = child_client.post("/goal", data={"target": "15", "next": "/account"})
    assert r.status_code == 200 and "All about me" in r.text and "0 of 15 this week" in r.text


def test_next_must_be_local(child_client):
    r = child_client.post("/goal", data={"target": "15", "next": "https://evil.example"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/practice"


def test_me_page_shows_pending(app, child_client, db, child):
    from datetime import timedelta
    set_goal(db, child, 15, _today(app) - timedelta(days=1) if _today(app).weekday() else _today(app))
    set_goal(db, child, 20, _today(app) if _today(app).weekday() else _today(app) + timedelta(days=1))
    html = child_client.get("/account").text
    assert "0 of 15 this week" in html and "From next week: 20" in html


def test_streak_shown_from_two_weeks(app, child_client, db, child, monkeypatch):
    from app.goals import GoalStatus
    import app.routes.practice as pr
    monkeypatch.setattr(pr, "goal_status", lambda *a: GoalStatus(10, 3, False, 3, None))
    assert "3 weeks in a row 🔥" in child_client.get("/practice").text


def test_parent_progress_shows_goal(app, parent_client, db, child):
    set_goal(db, child, 15, _today(app))
    html = parent_client.get(f"/progress?user={child.id}").text
    assert "0 of 15 this week" in html


def test_parent_progress_without_goal(parent_client, child):
    assert "hasn't set a weekly goal" in parent_client.get(f"/progress?user={child.id}").text
