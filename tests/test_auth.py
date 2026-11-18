from tests.conftest import login_as


def test_login_redirects_by_role(client, parent, child):
    assert login_as(client, "dad").headers["location"] == "/parent"


def test_child_login_redirects_to_practice(client, child):
    assert login_as(client, "kid").headers["location"] == "/practice"


def test_bad_password_shows_error(client, parent):
    r = client.post("/login", data={"username": "dad", "password": "x"})
    assert r.status_code == 401 and "Wrong username or password" in r.text


def test_anonymous_redirected(client):
    r = client.get("/practice", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_child_blocked_from_parent_pages(child_client):
    assert child_client.get("/parent").status_code == 403


def test_logout(child_client):
    child_client.post("/logout")
    assert child_client.get("/practice", follow_redirects=False).headers["location"] == "/login"


def test_login_page_renders(client):
    r = client.get("/login")
    assert r.status_code == 200 and 'name="password"' in r.text
