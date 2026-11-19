"""Everyone can change their name and password; kids can fill in a fun profile."""
import pytest
from fastapi.testclient import TestClient

from app.auth import verify_password
from app.models import User
from app.profile import AVATARS, number_fact
from tests.conftest import login_as


def _user(db, username):
    db.expire_all()
    return db.query(User).filter_by(username=username).one()


def test_account_link_in_nav(child_client, parent_client):
    assert 'href="/account"' in child_client.get("/practice").text
    assert 'href="/account"' in parent_client.get("/parent").text


def test_account_needs_login(app):
    r = TestClient(app).get("/account", follow_redirects=False)
    assert r.status_code in (302, 303) and "/login" in r.headers["location"]


# ---- name ----

def test_change_name(child_client, db):
    r = child_client.post("/account/profile", data={"display_name": "  Arjun  "})
    assert r.status_code == 200 and "Saved" in r.text
    assert _user(db, "kid").display_name == "Arjun"


def test_name_cannot_be_blank(child_client, db):
    r = child_client.post("/account/profile", data={"display_name": "   "})
    assert r.status_code == 400 and _user(db, "kid").display_name == "Kid"


def test_name_length_capped(child_client, db):
    r = child_client.post("/account/profile", data={"display_name": "x" * 41})
    assert r.status_code == 400


def test_parent_changes_name(parent_client, db):
    parent_client.post("/account/profile", data={"display_name": "Papa"})
    assert _user(db, "dad").display_name == "Papa"


# ---- fun profile (kids only) ----

def test_kid_sees_fun_fields(child_client):
    html = child_client.get("/account").text
    for field in ("avatar", "favourite_game", "favourite_food", "favourite_animal", "superpower",
                  "favourite_number"):
        assert f'name="{field}"' in html


def test_parent_does_not_see_fun_fields(parent_client):
    html = parent_client.get("/account").text
    assert 'name="favourite_game"' not in html and 'name="display_name"' in html


def test_kid_saves_fun_profile(child_client, db):
    child_client.post("/account/profile", data={
        "display_name": "Kid", "avatar": AVATARS[1], "favourite_game": " Minecraft ",
        "favourite_food": "Nasi lemak", "favourite_animal": "", "superpower": "Flying",
        "favourite_number": "28"})
    p = _user(db, "kid").profile
    assert p == {"avatar": AVATARS[1], "favourite_game": "Minecraft", "favourite_food": "Nasi lemak",
                 "superpower": "Flying", "favourite_number": 28}
    html = child_client.get("/account").text
    assert 'value="Minecraft"' in html and 'value="28"' in html


def test_unknown_avatar_ignored(child_client, db):
    child_client.post("/account/profile", data={"display_name": "Kid", "avatar": "<b>x</b>"})
    assert "avatar" not in (_user(db, "kid").profile or {})


def test_fun_text_capped(child_client, db):
    r = child_client.post("/account/profile", data={"display_name": "Kid", "favourite_game": "x" * 61})
    assert r.status_code == 400


def test_bad_favourite_number(child_client, db):
    r = child_client.post("/account/profile", data={"display_name": "Kid", "favourite_number": "lots"})
    assert r.status_code == 400 and "number" in r.text


def test_parent_cannot_store_fun_fields(parent_client, db):
    parent_client.post("/account/profile", data={"display_name": "Dad", "favourite_game": "Chess"})
    assert not _user(db, "dad").profile


def test_practice_home_greets_with_avatar_and_number(child_client, db):
    child_client.post("/account/profile", data={"display_name": "Arjun", "avatar": AVATARS[0],
                                                "favourite_number": "7"})
    html = child_client.get("/practice").text
    assert f"Hi {AVATARS[0]} Arjun!" in html and "7 is a prime number" in html


@pytest.mark.parametrize("n,phrase", [
    (7, "prime"), (28, "perfect number"), (64, "square"), (27, "cube"), (10, "triangular"),
    (34, "Fibonacci"), (0, "zero"), (1, "1"), (100, "square"),
])
def test_number_facts(n, phrase):
    assert phrase in number_fact(n)


def test_number_fact_for_plain_number():
    assert number_fact(22)  # always says something


# ---- password ----

def _pw(client, current="pw", new="newpass1", confirm=None):
    return client.post("/account/password", data={"current_password": current, "new_password": new,
                                                  "confirm_password": new if confirm is None else confirm})


def test_change_password(child_client, db, app):
    r = _pw(child_client)
    assert r.status_code == 200 and "Password changed" in r.text
    assert verify_password("newpass1", _user(db, "kid").password_hash)
    c = TestClient(app)
    assert login_as(c, "kid", "pw").status_code == 401
    assert login_as(c, "kid", "newpass1").status_code == 303


def test_wrong_current_password(child_client, db):
    r = _pw(child_client, current="nope")
    assert r.status_code == 400 and "current password" in r.text
    assert verify_password("pw", _user(db, "kid").password_hash)


def test_passwords_must_match(child_client, db):
    r = _pw(child_client, confirm="different1")
    assert r.status_code == 400 and "match" in r.text


def test_password_too_short(child_client):
    r = _pw(child_client, new="abc")
    assert r.status_code == 400 and "6" in r.text


def test_password_change_signs_out_other_devices(app, child, db):
    a, b = TestClient(app), TestClient(app)
    login_as(a, "kid")
    login_as(b, "kid")
    assert _pw(a).status_code == 200
    assert a.get("/practice", follow_redirects=False).status_code == 200  # this device stays in
    assert b.get("/practice", follow_redirects=False).status_code in (302, 303)  # the other is signed out


def test_wrong_current_password_locks_out(child_client, monkeypatch):
    import app.auth as auth
    monkeypatch.setattr(auth, "FAIL_LIMIT", 3)
    for _ in range(3):
        _pw(child_client, current="nope")
    r = _pw(child_client)  # even the right one is refused for a while
    assert r.status_code == 429
