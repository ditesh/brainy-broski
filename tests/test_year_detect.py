"""Working out a paper's year from its file name, its first pages, its link, or Claude."""
import pymupdf as fitz

from app.ai.schemas import PdfStructure
from app.importer.pipeline import detect_structure
from app.importer.year import UNKNOWN_YEAR, guess_year
from app.models import ImportStatus, SourcePdf
from tests.fixtures.make_pdf import build_contest_pdf, contest_layout, contest_structure_dict


def _pdf(tmp_path, *page_texts):
    doc = fitz.open()
    for t in page_texts:
        doc.new_page().insert_text((72, 72), t)
    path = tmp_path / "p.pdf"
    doc.save(path)
    return path


def test_year_from_file_name(tmp_path):
    assert guess_year("imonst-2020-problems-w-answers.pdf", "", _pdf(tmp_path, "Problem 1.")) == 2020


def test_year_from_pdf_text(tmp_path):
    p = _pdf(tmp_path, "International Mathematical Olympiad National Selection Test 2021",
             "Junior category, IMONST 2021")
    assert guess_year("paper.pdf", "", p) == 2021


def test_most_common_year_in_text_wins(tmp_path):
    p = _pdf(tmp_path, "SASMO 2019 Grade 7. Copyright 2020", "SASMO 2019")
    assert guess_year("paper.pdf", "", p) == 2019


def test_year_from_link_when_nothing_else(tmp_path):
    url = "https://imo-malaysia.org/wp-content/uploads/2022/09/problems.pdf"
    assert guess_year("problems.pdf", url, _pdf(tmp_path, "Problem 1.")) == 2022


def test_file_name_beats_link(tmp_path):
    url = "https://imo-malaysia.org/wp-content/uploads/2021/02/imonst-2020-problems.pdf"
    assert guess_year("imonst-2020-problems.pdf", url, _pdf(tmp_path, "x")) == 2020


def test_no_year_found(tmp_path):
    assert guess_year("paper.pdf", "", _pdf(tmp_path, "Problem 1. 1234 apples")) is None


def test_ignores_implausible_years(tmp_path):
    assert guess_year("answers-1850-3000.pdf", "", _pdf(tmp_path, "x")) is None


def test_unreadable_pdf_is_fine(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.4 garbage")
    assert guess_year("imonst-2020.pdf", "", bad) == 2020


# ---- upload route ----

def test_upload_without_year_uses_file_name(parent_client, fake_ai, db, tmp_path):
    fake_ai.add(PdfStructure, PdfStructure.model_validate(contest_structure_dict()))
    data = build_contest_pdf(tmp_path / "u.pdf", contest_layout()).read_bytes()
    parent_client.post("/parent/import", data={"contest": "IMONST1", "year": ""},
                       files={"file": ("imonst-2020-problems.pdf", data, "application/pdf")})
    assert db.query(SourcePdf).one().year == 2020


def test_typed_year_wins(parent_client, fake_ai, db, tmp_path):
    fake_ai.add(PdfStructure, PdfStructure.model_validate(contest_structure_dict()))
    data = build_contest_pdf(tmp_path / "u.pdf", contest_layout()).read_bytes()
    parent_client.post("/parent/import", data={"contest": "IMONST1", "year": "2019"},
                       files={"file": ("imonst-2020-problems.pdf", data, "application/pdf")})
    assert db.query(SourcePdf).one().year == 2019


def test_upload_form_year_optional(parent_client):
    html = parent_client.get("/parent/import").text
    assert 'name="year"' in html and "work it out" in html
    assert 'name="year" value=' not in html  # no pre-filled guess


# ---- Claude as the fallback ----

def _src(db, settings, year):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    path = build_contest_pdf(settings.data_dir / "s.pdf", contest_layout())
    s = SourcePdf(filename="s.pdf", path=str(path), contest="IMONST1", year=year, status=ImportStatus.pending)
    db.add(s)
    db.commit()
    return s


def test_claude_fills_unknown_year(db, settings, fake_ai):
    s = _src(db, settings, UNKNOWN_YEAR)
    fake_ai.add(PdfStructure, PdfStructure.model_validate({**contest_structure_dict(), "year": 2018}))
    detect_structure(s.id, db, fake_ai, settings)
    db.refresh(s)
    assert s.year == 2018


def test_claude_does_not_override_known_year(db, settings, fake_ai):
    s = _src(db, settings, 2020)
    fake_ai.add(PdfStructure, PdfStructure.model_validate({**contest_structure_dict(), "year": 2018}))
    detect_structure(s.id, db, fake_ai, settings)
    db.refresh(s)
    assert s.year == 2020


def test_unknown_year_displayed_nicely(parent_client, db, settings):
    s = _src(db, settings, UNKNOWN_YEAR)
    s.status = ImportStatus.needs_review
    db.commit()
    html = parent_client.get("/parent").text
    assert "IMONST1 0" not in html and "year unknown" in html
