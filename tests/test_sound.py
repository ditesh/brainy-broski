"""Sounds: on by default for kids, a mute toggle that follows him across logins."""
from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import login_as


def test_sound_on_by_default(child_client):
    assert 'data-sound-pref="on"' in child_client.get("/practice").text


def test_toggle_sound(app, child_client):
    r = child_client.post("/sound", data={"on": "0", "next": "/practice"})
    assert 'data-sound-pref="off"' in r.text
    other = TestClient(app)
    login_as(other, "kid")
    assert 'data-sound-pref="off"' in other.get("/practice").text
    child_client.post("/sound", data={"on": "1"})
    assert 'data-sound-pref="on"' in child_client.get("/practice").text


def test_toggle_on_home_and_results(child_client, db, child, junior_paper):
    from app.practice.service import save_answer, start_attempt, submit
    assert 'action="/sound"' in child_client.get("/practice").text
    a = start_attempt(db, child, junior_paper, "practice", [1])
    save_answer(db, a, 1, "1")
    submit(db, a)
    assert 'action="/sound"' in child_client.get(f"/attempts/{a.id}/results").text


def test_parents_get_no_sound(parent_client):
    html = parent_client.get("/parent").text
    assert 'data-sound-pref="off"' in html and 'action="/sound"' not in html
    assert parent_client.post("/sound", data={"on": "1"}).status_code == 403


def test_sound_js_defines_all_sounds():
    js = Path("app/static/sound.js").read_text()
    for name in ("ding", "crack", "fanfare", "jingle", "squeak"):
        assert f"{name}:" in js
    assert "AudioContext" in js and "sound-pref" in js


def test_sound_js_loaded(child_client):
    assert "/static/sound.js" in child_client.get("/practice").text


def test_waiting_sounds_expire():
    js = Path("app/static/sound.js").read_text()
    assert js.count("Date.now() - queuedAt < QUEUE_MS") == 2
