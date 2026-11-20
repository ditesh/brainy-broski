"""Top-bar tabs look like tabs: no underline, and the current page is marked."""
import re
from pathlib import Path

CSS = Path("app/static/app.css").read_text()


def test_tabs_never_underlined():
    rule = re.search(r"\.topbar nav a[^{]*\{([^}]*)\}", CSS)
    assert rule and "text-decoration: none" in rule.group(1)
    hover = re.search(r"\.topbar nav a:hover[^{]*\{([^}]*)\}", CSS)
    assert hover and "text-decoration: none" in hover.group(1)


def test_current_tab_marked_for_child(child_client):
    html = child_client.get("/progress").text
    assert '<a href="/progress" aria-current="page"' in html
    assert '<a href="/practice" aria-current' not in html


def test_current_tab_marked_on_sub_pages(parent_client):
    html = parent_client.get("/parent/import").text
    assert '<a href="/parent" aria-current="page"' in html


def test_account_tab_marked(child_client):
    assert '<a href="/account" aria-current="page"' in child_client.get("/account").text


def test_back_links_never_underlined():
    rule = re.search(r"a\.back:hover[^{]*\{([^}]*)\}", CSS)
    assert rule and "text-decoration: none" in rule.group(1)
