"""Home page: picking a challenge stays in view; the fun extras sit in a side column."""
import re


def test_picker_links_keep_the_scroll_position(child_client, papers):
    html = child_client.get("/practice").text
    pills = re.findall(r'<a class="pill"[^>]*>', html)
    assert pills and all("data-keep-scroll" in a for a in pills)
    assert "bb-keep-scroll" in html          # the script that puts the page back where it was


def test_extras_sit_in_the_side_column(child_client, db, child, papers):
    html = child_client.get("/practice").text
    side = html[html.index('class="home-side"'):html.index('class="home-main"')]
    main = html[html.index('class="home-main"'):]
    for part in ("mission-hero", "goal-card", "brain-break", 'id="wonder"'):
        assert part in side, part
    assert 'id="pick"' in main and "mission-hero" not in main


def test_home_column_is_wider(child_client):
    css = open("app/static/app.css").read()
    assert ".home-layout" in css and "grid-template-columns" in css.split(".home-layout", 1)[1]
