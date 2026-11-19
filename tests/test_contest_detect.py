"""Working out which contest a paper is from: file name, link, first pages, then Claude."""
import pymupdf as fitz
import pytest

from app.ai.schemas import PdfStructure
from app.importer.contest import guess_contest
from app.importer.pipeline import detect_structure
from app.models import ImportStatus, SourcePdf
from tests.fixtures.make_pdf import build_contest_pdf, contest_layout, contest_structure_dict


def _pdf(tmp_path, *page_texts):
    doc = fitz.open()
    for t in page_texts or ("Problem 1.",):
        doc.new_page().insert_text((72, 72), t)
    path = tmp_path / "p.pdf"
    doc.save(path)
    return path


@pytest.mark.parametrize("name,expected", [
    ("2019-SASMO-G8.pdf", "SASMO"),
    ("imonst-2020-problems-w-answers.pdf", "IMONST1"),
    ("IMONST1_2022_Junior.pdf", "IMONST1"),
    ("imonst-2-2021.pdf", "IMONST2"),
    ("IMONST2 2023 solutions.pdf", "IMONST2"),
    ("kangaroo_2018_student.pdf", "Kangaroo"),
    ("ASMO-2019-Grade6.pdf", "ASMO"),
])
def test_contest_from_file_name(tmp_path, name, expected):
    assert guess_contest(name, "", _pdf(tmp_path)) == expected


def test_contest_from_link(tmp_path):
    url = "https://simcc.org/wp-content/uploads/2025/03/2019-SASMO-G8.pdf"
    assert guess_contest("paper.pdf", url, _pdf(tmp_path)) == "SASMO"


def test_link_host_counts(tmp_path):
    assert guess_contest("problems.pdf", "https://imo-malaysia.org/wp-content/uploads/problems.pdf",
                         _pdf(tmp_path)) == "IMONST1"


def test_contest_from_pdf_text(tmp_path):
    p = _pdf(tmp_path, "Singapore and Asian Schools Math Olympiad", "Grade 8 contest")
    assert guess_contest("paper.pdf", "", p) == "SASMO"


def test_kangaroo_from_text(tmp_path):
    assert guess_contest("x.pdf", "", _pdf(tmp_path, "International Mathematical Kangaroo 2019")) == "Kangaroo"


def test_asmo_not_confused_with_sasmo(tmp_path):
    assert guess_contest("sasmo.pdf", "", _pdf(tmp_path)) == "SASMO"
    assert guess_contest("x.pdf", "", _pdf(tmp_path, "Asian Science and Mathematics Olympiad")) == "ASMO"


def test_imonst_year_is_not_round_two(tmp_path):
    assert guess_contest("imonst-2021.pdf", "", _pdf(tmp_path)) == "IMONST1"


def test_unknown(tmp_path):
    assert guess_contest("paper.pdf", "", _pdf(tmp_path, "Problem 1. Find x.")) is None


# ---- upload route ----

def _upload(client, tmp_path, filename, contest=None):
    data = build_contest_pdf(tmp_path / "u.pdf", contest_layout()).read_bytes()
    form = {"year": ""} if contest is None else {"year": "", "contest": contest}
    return client.post("/parent/import", data=form, files={"file": (filename, data, "application/pdf")})


def test_form_offers_auto_contest(parent_client):
    html = parent_client.get("/parent/import").text
    assert '<option value="">Work it out from the file</option>' in html


def test_upload_without_contest_uses_file_name(parent_client, fake_ai, db, tmp_path):
    fake_ai.add(PdfStructure, PdfStructure.model_validate(contest_structure_dict()))
    _upload(parent_client, tmp_path, "2019-SASMO-G8.pdf")
    assert db.query(SourcePdf).one().contest == "SASMO"


def test_chosen_contest_wins(parent_client, fake_ai, db, tmp_path):
    fake_ai.add(PdfStructure, PdfStructure.model_validate(contest_structure_dict()))
    _upload(parent_client, tmp_path, "2019-SASMO-G8.pdf", contest="ASMO")
    assert db.query(SourcePdf).one().contest == "ASMO"


def test_upload_rejects_made_up_contest(parent_client, db, tmp_path):
    r = _upload(parent_client, tmp_path, "x.pdf", contest="<script>")
    assert r.status_code == 400 and db.query(SourcePdf).count() == 0


# ---- Claude as the fallback ----

def _src(db, settings, contest):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    path = build_contest_pdf(settings.data_dir / "s.pdf", contest_layout())
    s = SourcePdf(filename="s.pdf", path=str(path), contest=contest, year=2020, status=ImportStatus.pending)
    db.add(s)
    db.commit()
    return s


def test_claude_fills_unknown_contest(db, settings, fake_ai):
    s = _src(db, settings, "")
    fake_ai.add(PdfStructure, PdfStructure.model_validate({**contest_structure_dict(), "contest": "Kangaroo"}))
    detect_structure(s.id, db, fake_ai, settings)
    db.refresh(s)
    assert s.contest == "Kangaroo"


def test_claude_does_not_override_known_contest(db, settings, fake_ai):
    s = _src(db, settings, "IMONST1")
    fake_ai.add(PdfStructure, PdfStructure.model_validate({**contest_structure_dict(), "contest": "Kangaroo"}))
    detect_structure(s.id, db, fake_ai, settings)
    db.refresh(s)
    assert s.contest == "IMONST1"


def test_unrecognised_contest_becomes_other(db, settings, fake_ai):
    s = _src(db, settings, "")
    fake_ai.add(PdfStructure, PdfStructure.model_validate({**contest_structure_dict(), "contest": "AMC 8"}))
    detect_structure(s.id, db, fake_ai, settings)
    db.refresh(s)
    assert s.contest == "Other"


def test_failed_detection_still_names_contest(db, settings, fake_ai):
    s = _src(db, settings, "")
    detect_structure(s.id, db, fake_ai, settings)  # fake AI has no answer queued: detection fails
    db.refresh(s)
    assert s.status == ImportStatus.failed and s.contest == "Other"
