def test_pages_link_favicon(client):
    html = client.get("/login").text
    assert 'rel="icon" href="/icon.svg' in html
    assert 'rel="apple-touch-icon" href="/static/apple-touch-icon.png"' in html


def test_favicon_files_served(client):
    svg = client.get("/static/favicon.svg")
    assert svg.status_code == 200 and "<svg" in svg.text
    png = client.get("/static/apple-touch-icon.png")
    assert png.status_code == 200 and png.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_favicon_ico_redirects(client):
    r = client.get("/favicon.ico", follow_redirects=False)
    assert r.status_code in (301, 307, 308) and r.headers["location"] == "/icon.svg"
