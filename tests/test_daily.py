"""Daily favicon symbol and daily maths fact."""
from datetime import date, datetime, timezone
from math import factorial

from freezegun import freeze_time

from app.daily import FACTS, SYMBOLS, fact_for, favicon_svg, local_today, symbol_for


def test_symbol_and_fact_change_day_to_day():
    d1, d2 = date(2026, 11, 18), date(2026, 11, 19)
    assert symbol_for(d1) != symbol_for(d2)
    assert fact_for(d1) != fact_for(d2)
    assert symbol_for(d1) == symbol_for(date(2026, 11, 18))  # stable within a day


def test_every_symbol_appears_over_a_cycle():
    start = date(2026, 1, 1).toordinal()
    seen = {symbol_for(date.fromordinal(start + i)).name for i in range(len(SYMBOLS))}
    assert seen == {s.name for s in SYMBOLS}


def test_favicon_svg_is_valid_and_named():
    import xml.etree.ElementTree as ET
    for s in SYMBOLS:
        root = ET.fromstring(favicon_svg(s))
        assert root.tag.endswith("svg")
        from html import escape
        assert escape(s.name) in favicon_svg(s)


def test_local_day_is_malaysia_not_utc():
    # 20:00 UTC on the 18th is 04:00 on the 19th in Kuala Lumpur
    with freeze_time(datetime(2026, 11, 18, 20, 0, tzinfo=timezone.utc)):
        assert local_today("Asia/Kuala_Lumpur") == date(2026, 11, 19)


def test_icon_route_serves_todays_symbol(client):
    with freeze_time("2026-11-18 03:00:00"):
        r = client.get("/icon.svg")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml")
    assert symbol_for(date(2026, 11, 18)).name in r.text
    assert "max-age" in r.headers["cache-control"]


def test_pages_use_daily_icon(client):
    html = client.get("/login").text
    assert 'rel="icon" href="/icon.svg' in html
    assert '<img src="/icon.svg' in html


def test_kid_sees_daily_fact(child_client, junior_paper, monkeypatch):
    import app.daily
    monkeypatch.setattr(app.daily, "local_today", lambda tz: date(2026, 11, 18))
    html = child_client.get("/practice").text
    f = fact_for(date(2026, 11, 18))
    assert "Today's maths wonder" in html
    assert f.title.replace("'", "&#39;") in html


def test_facts_well_formed():
    assert len(FACTS) >= 40
    assert len({f.title for f in FACTS}) == len(FACTS)
    for f in FACTS:
        assert f.title and f.body and f.why
        assert f.body.count("$") % 2 == 0 and f.why.count("$") % 2 == 0


# The facts are shown to a child as true: check the numeric ones.
def test_numeric_claims_hold():
    for n in (532, 821, 910, 631):
        r = int(str(n)[::-1].rjust(3, "0"))
        d = abs(n - r)
        assert d + int(str(d).rjust(3, "0")[::-1]) == 1089
    assert 111111111 ** 2 == 12345678987654321
    assert sum(range(1, 101)) == 5050
    assert 918082 % 11 == 0
    assert [142857 * k for k in range(1, 7)] == [142857, 285714, 428571, 571428, 714285, 857142]
    assert 142857 * 7 == 999999
    assert 1 ** 3 + 12 ** 3 == 9 ** 3 + 10 ** 3 == 1729
    assert sum(k * k for k in range(1, 9)) == 204
    assert factorial(10) == 6 * 7 * 24 * 60 * 60
    z, n = 0, factorial(100)
    while n % 10 == 0:
        n //= 10
        z += 1
    assert z == 24
    assert 2 * 2 * 2 * 3 * 3 * 5 == 360
    assert all(sq % 8 == 1 for sq in (k * k for k in range(1, 100, 2)))
    assert sum(k ** 3 for k in range(1, 11)) == sum(range(1, 11)) ** 2
    assert 99 * 101 == 9999 and 35 * 35 == 1225 and 11 * 43 == 473
    assert 0.1e-3 * 2 ** 42 / 1000 > 384_400  # km, paper folded 42 times passes the Moon
    from math import comb
    p_all_different = 1.0
    for k in range(23):
        p_all_different *= (365 - k) / 365
    assert 1 - p_all_different > 0.5
    assert comb(10, 2) == 45 and 6 * 3 // 2 == 9
    assert 1 + 2 + 4 + 7 + 14 == 28
    assert {k * k % 10 for k in range(100)} == {0, 1, 4, 5, 6, 9}


def test_dropped_symbols_not_used():
    assert not {"∠", "!", "%"} & {s.glyph for s in SYMBOLS}


def _fix_day(monkeypatch, d):
    import app.daily
    monkeypatch.setattr(app.daily, "local_today", lambda tz: d)


def test_dismiss_hides_wonder_for_the_day(child_client, junior_paper, monkeypatch):
    _fix_day(monkeypatch, date(2026, 11, 18))
    assert "Today's maths wonder" in child_client.get("/practice").text
    r = child_client.post("/wonder/dismiss", headers={"HX-Request": "true"})
    assert r.status_code == 200 and r.text == ""
    assert "Today's maths wonder" not in child_client.get("/practice").text


def test_wonder_returns_next_day(child_client, junior_paper, monkeypatch):
    _fix_day(monkeypatch, date(2026, 11, 18))
    child_client.post("/wonder/dismiss")
    _fix_day(monkeypatch, date(2026, 11, 19))
    assert "Today's maths wonder" in child_client.get("/practice").text


def test_dismiss_without_js_redirects(child_client, junior_paper):
    r = child_client.post("/wonder/dismiss", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/practice"


def test_dismiss_needs_login(client):
    r = client.post("/wonder/dismiss", follow_redirects=False)
    assert r.status_code in (303, 401, 403)
