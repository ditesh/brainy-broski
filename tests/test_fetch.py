import httpx
import pytest

from app.ai.schemas import PdfStructure
from app.fetch import FetchError, fetch_pdf
from app.models import SourcePdf
from tests.fixtures.make_pdf import contest_structure_dict

PDF = b"%PDF-1.5\n" + b"x" * 100
PUBLIC = lambda host: ["93.184.216.34"]  # noqa: E731


def transport(routes):
    def handler(request):
        r = routes.get(str(request.url))
        if r is None:
            return httpx.Response(404)
        return r
    return httpx.MockTransport(handler)


def test_fetches_pdf_and_names_it():
    t = transport({"https://example.org/papers/imonst-2020.pdf": httpx.Response(200, content=PDF)})
    name, data = fetch_pdf("https://example.org/papers/imonst-2020.pdf", transport=t, resolve=PUBLIC)
    assert name == "imonst-2020.pdf" and data == PDF


def test_follows_redirect():
    t = transport({"https://example.org/a": httpx.Response(302, headers={"location": "https://example.org/b.pdf"}),
                   "https://example.org/b.pdf": httpx.Response(200, content=PDF)})
    assert fetch_pdf("https://example.org/a", transport=t, resolve=PUBLIC)[1] == PDF


@pytest.mark.parametrize("url", ["ftp://example.org/x.pdf", "file:///etc/passwd", "not a url", ""])
def test_rejects_non_http(url):
    with pytest.raises(FetchError):
        fetch_pdf(url, transport=transport({}), resolve=PUBLIC)


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254", "::1", "fdaa::3"])
def test_rejects_private_addresses(ip):
    with pytest.raises(FetchError, match="private"):
        fetch_pdf("http://internal.example/x.pdf", transport=transport({}), resolve=lambda h: [ip])


def test_redirect_to_private_address_rejected():
    t = transport({"https://example.org/a": httpx.Response(302, headers={"location": "http://evil.example/x"})})
    resolve = lambda h: ["127.0.0.1"] if h == "evil.example" else ["93.184.216.34"]  # noqa: E731
    with pytest.raises(FetchError, match="private"):
        fetch_pdf("https://example.org/a", transport=t, resolve=resolve)


def test_not_a_pdf():
    t = transport({"https://example.org/page": httpx.Response(200, content=b"<html>hi</html>")})
    with pytest.raises(FetchError, match="isn't a PDF"):
        fetch_pdf("https://example.org/page", transport=t, resolve=PUBLIC)


def test_http_error():
    with pytest.raises(FetchError, match="404"):
        fetch_pdf("https://example.org/missing.pdf", transport=transport({}), resolve=PUBLIC)


def test_too_large():
    t = transport({"https://example.org/big.pdf": httpx.Response(200, content=PDF + b"x" * 2000)})
    with pytest.raises(FetchError, match="too big"):
        fetch_pdf("https://example.org/big.pdf", transport=t, resolve=PUBLIC, max_bytes=1000)


# ---- route ----

def test_import_from_url(parent_client, app, db, fake_ai):
    app.state.http_transport = transport({"https://example.org/imonst.pdf": httpx.Response(200, content=PDF)})
    app.state.resolve_host = PUBLIC
    fake_ai.add(PdfStructure, PdfStructure.model_validate(contest_structure_dict()))
    r = parent_client.post("/parent/import", data={"contest": "IMONST1", "year": "2020",
                                                   "url": "https://example.org/imonst.pdf"}, follow_redirects=False)
    assert r.status_code == 303
    src = db.query(SourcePdf).one()
    assert src.filename == "imonst.pdf"


def test_import_url_error_shown(parent_client, app):
    app.state.http_transport = transport({})
    app.state.resolve_host = PUBLIC
    r = parent_client.post("/parent/import", data={"contest": "IMONST1", "year": "2020",
                                                   "url": "https://example.org/nope.pdf"})
    assert r.status_code == 400 and "404" in r.text


def test_import_needs_file_or_url(parent_client):
    r = parent_client.post("/parent/import", data={"contest": "IMONST1", "year": "2020"})
    assert r.status_code == 400 and "Choose a PDF file or paste a link" in r.text


def test_form_has_url_field(parent_client):
    assert 'name="url"' in parent_client.get("/parent/import").text
