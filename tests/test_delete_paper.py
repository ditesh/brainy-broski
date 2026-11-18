"""Parent can delete an uploaded PDF with everything that hangs off it."""
from app.models import (Attempt, FollowupResponse, ImportStatus, Paper, PaperQuestion, Problem, Response,
                        SourcePdf, UploadToken, utcnow)
from app.practice.service import save_answer, start_attempt, submit


def _attempt_with_photo(db, settings, child, paper):
    a = start_attempt(db, child, paper, "practice", [2])
    save_answer(db, a, 2, "99")
    submit(db, a)
    r = a.responses[0]
    photo = settings.data_dir / "photos" / str(child.id) / f"{r.id}.jpg"
    photo.parent.mkdir(parents=True, exist_ok=True)
    photo.write_bytes(b"jpg")
    r.photo_path = str(photo.relative_to(settings.data_dir))
    db.add(UploadToken(token="t" * 32, response_id=r.id, expires_at=utcnow()))
    db.commit()
    return a, photo


def test_delete_removes_everything(parent_client, db, settings, contest_src, papers, child):
    a, photo = _attempt_with_photo(db, settings, child, papers["Junior"])
    other_paper_problem = papers["Primary"].questions[0].problem_id
    db.add(FollowupResponse(user_id=child.id, problem_id=other_paper_problem, answer="1", correct=False,
                            from_response_id=a.responses[0].id))
    db.commit()
    pdf = settings.data_dir / "pdfs" / "1.pdf"
    crops = settings.data_dir / "crops" / str(contest_src.id)
    assert pdf.exists() and crops.exists()

    resp = parent_client.post(f"/parent/import/{contest_src.id}/delete", follow_redirects=False)
    assert resp.status_code == 303 and resp.headers["location"] == "/parent"
    db.expire_all()
    for model in (SourcePdf, Paper, PaperQuestion, Problem, Attempt, Response, UploadToken, FollowupResponse):
        assert db.query(model).count() == 0, model
    assert not pdf.exists() and not crops.exists() and not photo.exists()


def test_delete_keeps_problems_shared_with_other_uploads(parent_client, db, settings, contest_src, papers):
    shared = papers["Junior"].questions[0].problem
    other = SourcePdf(filename="x.pdf", path=str(settings.data_dir / "pdfs" / "x.pdf"), contest="IMONST",
                      year=2021, status=ImportStatus.done)
    db.add(other)
    db.flush()
    p2 = Paper(source_pdf_id=other.id, category="Junior", language="English")
    db.add(p2)
    db.flush()
    db.add(PaperQuestion(paper_id=p2.id, number=1, part="", points=1, problem_id=shared.id, crop_paths=[]))
    db.commit()
    parent_client.post(f"/parent/import/{contest_src.id}/delete")
    db.expire_all()
    assert db.get(Problem, shared.id) is not None
    assert db.query(Paper).count() == 1


def test_confirm_page_lists_what_goes(parent_client, db, settings, contest_src, papers, child):
    _attempt_with_photo(db, settings, child, papers["Junior"])
    html = parent_client.get(f"/parent/import/{contest_src.id}/delete").text
    assert "Junior" in html and "Primary" in html
    assert "1 attempt" in html
    assert "Unpublish" in html  # offers the keep-history alternative


def test_cannot_delete_while_importing(parent_client, db, contest_src):
    contest_src.status = ImportStatus.running
    db.commit()
    assert parent_client.post(f"/parent/import/{contest_src.id}/delete").status_code == 400
    db.expire_all()
    assert db.get(SourcePdf, contest_src.id) is not None


def test_child_cannot_delete(child_client, db, contest_src):
    child_client.post(f"/parent/import/{contest_src.id}/delete")
    db.expire_all()
    assert db.get(SourcePdf, contest_src.id) is not None


def test_parent_home_has_delete_link(parent_client, contest_src):
    assert f"/parent/import/{contest_src.id}/delete" in parent_client.get("/parent").text


def test_delete_with_redo_chain(parent_client, db, settings, contest_src, papers, child):
    from app.practice.service import start_redo
    a, _ = _attempt_with_photo(db, settings, child, papers["Junior"])
    redo = start_redo(db, a)
    save_answer(db, redo, 2, "98")
    submit(db, redo)
    start_redo(db, redo)  # redo of the redo, left open
    assert parent_client.post(f"/parent/import/{contest_src.id}/delete").status_code == 200
    db.expire_all()
    assert db.query(Attempt).count() == 0
