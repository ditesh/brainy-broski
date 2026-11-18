"""The 'Import settings' page after an import has finished."""
from app.models import ImportStatus, Paper


def _done(db, src):
    src.status = ImportStatus.done
    db.commit()


def test_no_done_banner_when_everything_published(parent_client, db, contest_src, papers):
    _done(db, contest_src)
    html = parent_client.get(f"/parent/import/{contest_src.id}").text
    assert "Done!" not in html


def test_done_banner_while_a_paper_needs_checking(parent_client, db, contest_src, imported_paper):
    _done(db, contest_src)
    assert "Check each paper" in parent_client.get(f"/parent/import/{contest_src.id}").text


def test_offers_levels_not_yet_imported(parent_client, db, contest_src, imported_paper):
    _done(db, contest_src)
    html = parent_client.get(f"/parent/import/{contest_src.id}").text
    assert "Import more levels" in html
    assert 'value="Primary"' in html and 'value="Junior"' not in html


def test_edit_details_updates_source_and_papers(parent_client, db, contest_src, papers):
    _done(db, contest_src)
    r = parent_client.post(f"/parent/import/{contest_src.id}/details",
                           data={"contest": "IMONST1", "year": "2021", "duration_min": "150"},
                           follow_redirects=False)
    assert r.status_code == 303
    db.expire_all()
    assert (contest_src.contest, contest_src.year, contest_src.duration_min) == ("IMONST1", 2021, 150)
    assert all(p.duration_min == 150 for p in db.query(Paper).all())


def test_edit_details_blank_duration_clears_timer(parent_client, db, contest_src, papers):
    parent_client.post(f"/parent/import/{contest_src.id}/details",
                       data={"contest": "IMONST1", "year": "2020", "duration_min": ""})
    db.expire_all()
    assert contest_src.duration_min is None
    assert all(p.duration_min is None for p in db.query(Paper).all())


def test_edit_details_rejects_unknown_contest(parent_client, db, contest_src):
    r = parent_client.post(f"/parent/import/{contest_src.id}/details",
                           data={"contest": "Hacked", "year": "2020", "duration_min": ""})
    assert r.status_code == 400


def test_details_form_shown(parent_client, db, contest_src, papers):
    _done(db, contest_src)
    html = parent_client.get(f"/parent/import/{contest_src.id}").text
    assert f'action="/parent/import/{contest_src.id}/details"' in html
