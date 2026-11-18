import io
import sqlite3

import pymupdf as fitz
import pytest
from PIL import Image
from sqlalchemy import inspect, text

from app.models import PaperQuestion
from app.pdf.render import extract_figures
from tests.conftest import get_pq


def _pdf_with_diagram(path):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 100), "Problem 1. Find the area of the shaded square below.", fontsize=11)
    page.draw_rect(fitz.Rect(200, 120, 320, 220), color=(0, 0, 0), fill=(0.8, 0.8, 0.8))  # diagram
    page.insert_text((195, 235), "A", fontsize=10)                                       # diagram label
    page.insert_text((72, 260), "Problem 2. Compute 1/2 + 1/3.", fontsize=11)
    page.draw_rect(fitz.Rect(150, 262, 170, 262.4), color=None, fill=(0, 0, 0))          # fraction bar
    buf = io.BytesIO()
    Image.new("RGB", (80, 60), "red").save(buf, "PNG")
    page.insert_text((72, 320), "Problem 3. What colour is the flag?", fontsize=11)
    page.insert_image(fitz.Rect(100, 330, 220, 420), stream=buf.getvalue())             # embedded picture
    doc.save(str(path))
    return path


@pytest.fixture
def diagram_pdf(tmp_path):
    return _pdf_with_diagram(tmp_path / "d.pdf")


def test_vector_diagram_extracted_with_label(diagram_pdf, tmp_path):
    figs = extract_figures(diagram_pdf, [[1, 60, 88, 540, 245]], tmp_path / "f", "q001")
    assert len(figs) == 1 and figs[0].exists()
    w, h = Image.open(figs[0]).size
    assert w > 200 and h > 150  # ~120x100pt (+label) at 200 dpi


def test_fraction_bar_is_not_a_figure(diagram_pdf, tmp_path):
    assert extract_figures(diagram_pdf, [[1, 60, 248, 540, 275]], tmp_path / "f", "q002") == []


def test_embedded_image_extracted(diagram_pdf, tmp_path):
    figs = extract_figures(diagram_pdf, [[1, 60, 308, 540, 430]], tmp_path / "f", "q003")
    assert len(figs) == 1


def test_real_style_text_only_question_has_no_figures(tmp_path):
    from tests.fixtures.make_pdf import SAMPLE_LAYOUT, build_contest_pdf
    pdf = build_contest_pdf(tmp_path / "s.pdf", SAMPLE_LAYOUT)
    assert extract_figures(pdf, [[1, 60, 60, 540, 200]], tmp_path / "f", "q") == []


# ---- import + display ----

def test_import_records_figure_paths(imported_paper, db):
    q = get_pq(db, imported_paper, 1)
    assert q.figure_paths == []


def test_attempt_shows_text_not_crop(child_client, db, junior_paper, child):
    from app.practice.service import start_attempt
    q = get_pq(db, junior_paper, 3)
    q.problem.transcription = "How many **odd** numbers are there below $10^8$?"
    db.commit()
    a = start_attempt(db, child, junior_paper, "practice", [3])
    html = child_client.get(f"/attempts/{a.id}?q=3").text
    assert "<strong>odd</strong>" in html and "$10^8$" in html
    assert 'class="qtext"' in html and "See the original" in html


def test_figures_placed_at_markers(child_client, db, junior_paper, child, settings):
    from app.practice.service import start_attempt
    q = get_pq(db, junior_paper, 4)
    q.problem.transcription = "Look at this:\n\n[[figure]]\n\nThen this:\n\n[[figure]]\n\nWhat is the answer?"
    q.figure_paths = ["figs/a.png", "figs/b.png", "figs/c.png"]
    db.commit()
    a = start_attempt(db, child, junior_paper, "practice", [4])
    html = child_client.get(f"/attempts/{a.id}?q=4").text
    i_a, i_b, i_c = html.index("figs/a.png"), html.index("figs/b.png"), html.index("figs/c.png")
    assert html.index("Look at this") < i_a < html.index("Then this") < i_b < html.index("What is the answer") < i_c
    assert "[[figure]]" not in html


def test_falls_back_to_crop_without_text(child_client, db, junior_paper, child):
    from app.practice.service import start_attempt
    q = get_pq(db, junior_paper, 5)
    q.problem.transcription = "  "
    db.commit()
    a = start_attempt(db, child, junior_paper, "practice", [5])
    html = child_client.get(f"/attempts/{a.id}?q=5").text
    assert 'class="qimg"' in html and "See the original" not in html


def test_ai_text_in_question_is_escaped(child_client, db, junior_paper, child):
    from app.practice.service import start_attempt
    q = get_pq(db, junior_paper, 6)
    q.problem.transcription = "<script>alert(1)</script> What is 2+2?"
    db.commit()
    a = start_attempt(db, child, junior_paper, "practice", [6])
    assert "<script>alert(1)</script>" not in child_client.get(f"/attempts/{a.id}?q=6").text


def test_parent_can_edit_transcription(parent_client, db, imported_paper):
    q = get_pq(db, imported_paper, 2)
    html = parent_client.get(f"/parent/papers/{imported_paper.id}/review").text
    assert 'name="transcription"' in html
    parent_client.post(f"/parent/questions/{q.id}/text", data={"transcription": "Fixed wording $x^2$"})
    db.refresh(q.problem)
    assert q.problem.transcription == "Fixed wording $x^2$"


def test_analyse_prompt_asks_for_figure_markers():
    from app.ai.prompts import ANALYSE_SYSTEM
    assert "[[figure]]" in ANALYSE_SYSTEM


# ---- existing databases ----

def test_old_database_gets_new_column(tmp_path):
    from app.db import Base, ensure_schema, make_engine
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("create table paper_question (id integer primary key, paper_id int, number int, part text, "
                "points int, problem_id int, crop_paths json, crop_boxes json)")
    con.commit()
    con.close()
    eng = make_engine(f"sqlite:///{path}")
    ensure_schema(eng)
    cols = {c["name"] for c in inspect(eng).get_columns("paper_question")}
    assert "figure_paths" in cols


def test_backfill_extracts_figures_for_old_questions(db, settings, imported_paper, session_factory):
    from app.importer.pipeline import backfill_figures
    for q in imported_paper.questions:
        q.figure_paths = None
    db.commit()
    n = backfill_figures(session_factory, settings)
    db.expire_all()
    assert n == 20 and all(q.figure_paths == [] for q in db.query(PaperQuestion))
