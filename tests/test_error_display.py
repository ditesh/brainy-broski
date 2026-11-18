import html as _html

from fastapi.testclient import TestClient

from app.ai.schemas import PdfStructure
from app.ai.client import AIError
from app.models import ImportStatus


def test_404_is_a_friendly_page(child_client):
    r = child_client.get("/no/such/page")
    assert r.status_code == 404 and r.headers["content-type"].startswith("text/html")
    assert "couldn't find that page" in _html.unescape(r.text) and 'class="alert' in r.text and '"detail"' not in r.text


def test_403_for_child_is_friendly(child_client):
    r = child_client.get("/parent")
    assert r.status_code == 403 and "for grown-ups" in r.text and 'href="/"' in r.text


def test_unhandled_error_is_friendly_500(app, child):
    def boom():
        raise RuntimeError("secret internals")
    app.add_api_route("/boom", boom)
    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/boom")
    assert r.status_code == 500 and "Something went wrong" in r.text and "secret internals" not in r.text


def test_htmx_errors_return_a_fragment(parent_client, child_client):
    r = child_client.get("/parent", headers={"HX-Request": "true"})
    assert r.status_code == 403 and "<html" not in r.text and 'class="alert' in r.text


def test_api_detail_message_shown(child_client, junior_paper):
    r = child_client.post("/practice/start", data={"paper_id": junior_paper.id, "mode": "practice", "part": "Part Z"})
    assert r.status_code == 400 and "No questions in that part." in r.text and '"detail"' not in r.text


def test_failed_import_shows_alert_with_actions(parent_client, fake_ai, db, tmp_path):
    from tests.fixtures.make_pdf import build_contest_pdf, contest_layout
    fake_ai.add(PdfStructure, AIError("Claude is busy right now. Try again in a minute."))
    r = parent_client.post("/parent/import", data={"contest": "IMONST1", "year": "2020"},
                           files={"file": ("p.pdf", build_contest_pdf(tmp_path / "p.pdf", contest_layout()).read_bytes(),
                                           "application/pdf")})
    html = _html.unescape(r.text)
    assert 'role="alert"' in html and "We couldn't read this paper" in html
    assert "Claude is busy right now" in html and "Retry" in html
    assert "Could not read the paper" not in html  # no technical prefix


def test_form_errors_use_alert(client, parent):
    r = client.post("/login", data={"username": "dad", "password": "nope"})
    assert 'class="alert error"' in r.text and "Wrong username or password" in r.text


def test_page_has_htmx_error_toast_handler(child_client):
    html = child_client.get("/practice").text
    assert "htmx:responseError" in html and 'id="toast"' in html
