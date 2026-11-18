"""Practice home: pick the competition first, then a level from that competition."""
from app.models import ImportStatus, Paper, SourcePdf
from app.practice.service import start_attempt


def _add(db, settings, contest, year, levels):
    s = SourcePdf(filename="x.pdf", path=str(settings.data_dir / "x.pdf"), contest=contest, year=year,
                  status=ImportStatus.done)
    db.add(s)
    db.flush()
    for lv in levels:
        db.add(Paper(source_pdf_id=s.id, category=lv, language="en", published=True))
    db.commit()


def test_competitions_listed_then_levels_of_chosen_one(child_client, db, settings, junior_paper):
    _add(db, settings, "Kangaroo", 2024, ["Benjamin", "Cadet"])
    html = child_client.get("/practice?contest=Kangaroo").text
    assert 'href="/practice?contest=IMONST"' in html and 'href="/practice?contest=Kangaroo"' in html
    assert "level=Benjamin" in html and "level=Cadet" in html
    assert "level=Junior" not in html  # IMONST's levels aren't offered for Kangaroo


def test_competition_comes_before_level(child_client, db, settings, junior_paper):
    html = child_client.get("/practice").text
    assert html.index("Which competition?") < html.index("Which level?")


def test_defaults_to_junior(child_client, junior_paper):
    html = child_client.get("/practice?contest=IMONST").text
    assert 'aria-current="true">Junior' in html
    assert "IMONST 2020 Junior" in html and "IMONST 2020 Primary" not in html


def test_defaults_to_last_practised(child_client, db, settings, child, papers):
    _add(db, settings, "Kangaroo", 2024, ["Benjamin", "Cadet"])
    cadet = db.query(Paper).filter_by(category="Cadet").one()
    from datetime import timedelta
    from app.models import Attempt, utcnow
    start_attempt(db, child, papers["Junior"], "practice", None)
    db.add(Attempt(user_id=child.id, paper_id=cadet.id, question_numbers=[], started_at=utcnow() + timedelta(minutes=1)))
    db.commit()
    html = child_client.get("/practice").text
    assert 'aria-current="true">Kangaroo' in html and 'aria-current="true">Cadet' in html


def test_unknown_level_falls_back(child_client, junior_paper):
    html = child_client.get("/practice?contest=IMONST&level=Nope").text
    assert 'aria-current="true">Junior' in html


def test_unknown_contest_falls_back(child_client, junior_paper):
    html = child_client.get("/practice?contest=Nope").text
    assert 'aria-current="true">IMONST' in html
