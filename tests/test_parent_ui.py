import io

from app.ai.client import AIError
from app.ai.schemas import PdfStructure
from app.models import ImportStatus, Paper, PaperQuestion, SourcePdf
from tests.conftest import get_pq
from tests.fixtures.make_pdf import build_contest_pdf, contest_layout, contest_structure_dict


def _pdf_bytes(tmp_path):
    return build_contest_pdf(tmp_path / "up.pdf", contest_layout()).read_bytes()


def test_upload_starts_structure_detection(parent_client, fake_ai, db, tmp_path):
    fake_ai.add(PdfStructure, PdfStructure.model_validate(contest_structure_dict()))
    r = parent_client.post("/parent/import", data={"contest": "IMONST1", "year": "2020", "duration_min": "180"},
                           files={"file": ("imonst.pdf", _pdf_bytes(tmp_path), "application/pdf")},
                           follow_redirects=False)
    assert r.status_code == 303
    src = db.query(SourcePdf).one()
    db.refresh(src)
    assert src.status == ImportStatus.needs_review and src.contest == "IMONST1"
    page = parent_client.get(r.headers["location"]).text
    assert 'value="Junior"' in page and 'value="Primary"' in page
    assert page.count('name="categories"') == 2  # Malay section not offered


def test_upload_rejects_non_pdf(parent_client):
    r = parent_client.post("/parent/import", data={"contest": "IMONST1", "year": "2020"},
                           files={"file": ("x.pdf", b"hello", "application/pdf")})
    assert r.status_code == 400 and "PDF" in r.text


def test_failed_structure_shows_retry(parent_client, fake_ai, db, tmp_path):
    fake_ai.add(PdfStructure, AIError("overloaded"))
    r = parent_client.post("/parent/import", data={"contest": "IMONST1", "year": "2020"},
                           files={"file": ("imonst.pdf", _pdf_bytes(tmp_path), "application/pdf")})
    assert "overloaded" in r.text and "Retry" in r.text


def test_choose_categories_runs_import(parent_client, contest_src, fake_ai, db):
    from app.ai.schemas import QuestionAnalysis
    from tests.support.contest import analysis_responder
    fake_ai.respond(QuestionAnalysis, analysis_responder)
    r = parent_client.post(f"/parent/import/{contest_src.id}", data={"categories": ["Junior"]})
    assert r.status_code == 200
    assert db.query(Paper).count() == 1 and db.query(PaperQuestion).count() == 20


def test_review_shows_crops_and_answers(parent_client, imported_paper):
    html = parent_client.get(f"/parent/papers/{imported_paper.id}/review").text
    assert html.count('class="qimg"') == 20 and 'value="18"' in html


def test_review_edit_answer(parent_client, imported_paper, db):
    q = get_pq(db, imported_paper, 2)
    r = parent_client.post(f"/parent/questions/{q.id}", data={"answer": " 5 ", "answer_type": "integer",
                                                              "points": "2", "tags": "parity, logic, bogus"})
    assert r.status_code == 200
    db.refresh(q)
    db.refresh(q.problem)
    assert (q.problem.answer, q.points, q.problem.tags) == ("5", 2, ["parity", "logic"])


def test_crop_nudge_moves_edges(parent_client, imported_paper, db):
    q = get_pq(db, imported_paper, 2)
    y0, y1 = q.crop_boxes[0][2], q.crop_boxes[-1][4]
    parent_client.post(f"/parent/questions/{q.id}/crop", data={"dy0": "-20", "dy1": "20"})
    db.refresh(q)
    assert q.crop_boxes[0][2] == y0 - 20 and q.crop_boxes[-1][4] == y1 + 20


def test_unlink_and_link(parent_client, papers, db):
    j1, p6 = get_pq(db, papers["Junior"], 1), get_pq(db, papers["Primary"], 6)
    assert j1.problem_id == p6.problem_id
    parent_client.post(f"/parent/questions/{j1.id}/unlink")
    db.refresh(j1)
    assert j1.problem_id != p6.problem_id and j1.problem.answer == p6.problem.answer
    parent_client.post(f"/parent/questions/{j1.id}/link", data={"other_pq_id": str(p6.id)})
    db.refresh(j1)
    assert j1.problem_id == p6.problem_id


def test_link_rejects_different_answers(parent_client, papers, db):
    a, b = get_pq(db, papers["Junior"], 7), get_pq(db, papers["Junior"], 8)
    r = parent_client.post(f"/parent/questions/{a.id}/link", data={"other_pq_id": str(b.id)})
    assert r.status_code == 400


def test_publish(parent_client, imported_paper, db):
    parent_client.post(f"/parent/papers/{imported_paper.id}/publish")
    db.refresh(imported_paper)
    assert imported_paper.published


def test_child_cannot_fetch_pdf_or_review(child_client, imported_paper):
    assert child_client.get(f"/parent/papers/{imported_paper.id}/review").status_code == 403
    assert child_client.get("/files/pdfs/1.pdf").status_code == 403


def test_child_can_fetch_crops(child_client, imported_paper):
    path = imported_paper.questions[0].crop_paths[0]
    assert child_client.get(f"/files/{path}").status_code == 200


def test_files_path_traversal_blocked(parent_client):
    assert parent_client.get("/files/%2e%2e/%2e%2e/etc/passwd").status_code == 404


def test_files_need_login(client, imported_paper):
    r = client.get(f"/files/{imported_paper.questions[0].crop_paths[0]}", follow_redirects=False)
    assert r.status_code == 303


def test_review_offers_link_candidates_with_same_answer(parent_client, papers, db):
    j1, p6 = get_pq(db, papers["Junior"], 1), get_pq(db, papers["Primary"], 6)
    parent_client.post(f"/parent/questions/{j1.id}/unlink")
    html = parent_client.get(f"/parent/papers/{papers['Junior'].id}/review").text
    assert f'<option value="{p6.id}">Primary Q6</option>' in html


def test_contest_choices_split_imonst_rounds(parent_client):
    html = parent_client.get("/parent/import").text
    assert "<option>IMONST1</option>" in html and "<option>IMONST2</option>" in html
    assert "<option>IMONST</option>" not in html
