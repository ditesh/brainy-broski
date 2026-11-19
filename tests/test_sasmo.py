"""SASMO-style papers: several years in one PDF, answers taken from worked solutions,
negative marking, and picture-based questions shown as the original."""
import pytest

from app.ai.schemas import PdfStructure, QuestionAnalysis
from app.importer.pipeline import choice_keys, run_import
from app.models import Paper, PaperQuestion, SourcePdf
from app.practice.service import save_answer, start_attempt, submit


def _parts(wrong_points=1):
    return [{"name": "Section A", "points": 2, "wrong_points": wrong_points, "first_question": 1, "last_question": 10},
            {"name": "Section B", "points": 4, "first_question": 11, "last_question": 20}]


def two_year_structure():
    # the synthetic contest PDF has English questions on pages 5-8 and 9-12; treat them as 2019 and 2020
    return {
        "year": 2019,
        "sections": [
            {"category": "Grade 8", "language": "en", "first_page": 5, "last_page": 8, "year": 2019, "parts": _parts()},
            {"category": "Grade 8", "language": "en", "first_page": 9, "last_page": 12, "year": 2020, "parts": _parts()},
        ],
        "answer_keys": [
            {"category": "Grade 8", "year": 2019, "page": 35,
             "answers": [{"question": n, "answer": "19"} for n in range(1, 21)]},
            {"category": "Grade 8", "year": 2020, "page": 46,
             "answers": [{"question": n, "answer": "20"} for n in range(1, 21)]},
        ],
    }


@pytest.fixture
def sasmo_src(db, contest_src):
    contest_src.contest, contest_src.year = "SASMO", 2019
    contest_src.structure = PdfStructure.model_validate(two_year_structure()).model_dump(mode="json")
    db.commit()
    return contest_src


@pytest.fixture
def plain_analysis(fake_ai):
    fake_ai.respond(QuestionAnalysis, lambda call: QuestionAnalysis(
        transcription="What is $1+1$?", answer_type="integer", tags=["parity"]))
    return fake_ai


def _import(db, settings, ai, src, keys):
    run_import(src.id, keys, db, ai, settings)
    return {p.year: p for p in db.query(Paper).filter_by(source_pdf_id=src.id).all()}


def test_years_are_separate_choices(sasmo_src):
    assert choice_keys(sasmo_src) == ["Grade 8 · 2019", "Grade 8 · 2020"]


def test_single_year_keys_unchanged(contest_src):
    assert choice_keys(contest_src) == ["Primary", "Junior"]


def test_status_page_offers_each_year(parent_client, sasmo_src):
    html = parent_client.get(f"/parent/import/{sasmo_src.id}").text
    assert 'value="Grade 8 · 2019"' in html and 'value="Grade 8 · 2020"' in html


def test_import_two_years_makes_two_papers(db, settings, plain_analysis, sasmo_src):
    papers = _import(db, settings, plain_analysis, sasmo_src, ["Grade 8 · 2019", "Grade 8 · 2020"])
    assert set(papers) == {2019, 2020}
    assert papers[2019].title == "SASMO 2019 Grade 8" and papers[2020].title == "SASMO 2020 Grade 8"
    a19 = {q.problem.answer for q in papers[2019].questions}
    a20 = {q.problem.answer for q in papers[2020].questions}
    assert a19 == {"19"} and a20 == {"20"}  # each year gets its own answers
    c19 = papers[2019].questions[0].crop_paths[0]
    c20 = papers[2020].questions[0].crop_paths[0]
    assert c19 != c20 and (settings.data_dir / c19).exists() and (settings.data_dir / c20).exists()


def test_import_one_year_only(db, settings, plain_analysis, sasmo_src):
    papers = _import(db, settings, plain_analysis, sasmo_src, ["Grade 8 · 2020"])
    assert set(papers) == {2020}


def test_more_years_offered_after_import(parent_client, db, settings, plain_analysis, sasmo_src):
    _import(db, settings, plain_analysis, sasmo_src, ["Grade 8 · 2019"])
    html = parent_client.get(f"/parent/import/{sasmo_src.id}").text
    more = html[html.index("Import more levels"):]
    assert 'value="Grade 8 · 2020"' in more and 'value="Grade 8 · 2019"' not in more


def test_source_label_shows_year_range(db, sasmo_src):
    assert sasmo_src.label == "SASMO 2019–2020"


# ---- negative marking ----

def test_wrong_answer_loses_points_blank_does_not(db, settings, plain_analysis, sasmo_src, child):
    p = _import(db, settings, plain_analysis, sasmo_src, ["Grade 8 · 2019"])[2019]
    p.published = True
    db.commit()
    q1 = next(q for q in p.questions if q.number == 1)
    q11 = next(q for q in p.questions if q.number == 11)
    assert (q1.points, q1.penalty) == (2, 1) and (q11.points, q11.penalty or 0) == (4, 0)
    a = start_attempt(db, child, p, "practice", [1, 2, 3, 11, 12])
    save_answer(db, a, 1, "19")   # right: +2
    save_answer(db, a, 2, "5")    # wrong in Section A: -1
    save_answer(db, a, 11, "5")   # wrong in Section B: 0
    # 3 and 12 left blank: 0
    submit(db, a)
    assert a.score == 2 - 1 and a.max_score == 2 * 3 + 4 * 2


def test_results_show_points_lost(child_client, db, settings, plain_analysis, sasmo_src, child):
    p = _import(db, settings, plain_analysis, sasmo_src, ["Grade 8 · 2019"])[2019]
    p.published = True
    db.commit()
    a = start_attempt(db, child, p, "practice", [2])
    save_answer(db, a, 2, "5")
    submit(db, a)
    assert "−1 point" in child_client.get(f"/attempts/{a.id}/results").text


def test_parent_can_set_penalty(parent_client, db, settings, plain_analysis, sasmo_src):
    p = _import(db, settings, plain_analysis, sasmo_src, ["Grade 8 · 2019"])[2019]
    q = p.questions[0]
    parent_client.post(f"/parent/questions/{q.id}", data={"answer": "19", "answer_type": "integer",
                                                         "points": "2", "penalty": "2", "tags": ""})
    db.expire_all()
    assert db.get(PaperQuestion, q.id).penalty == 2


def test_wrong_points_must_be_non_negative():
    from app.ai.schemas import Part
    assert Part(name="A", points=2, wrong_points=-1, first_question=1, last_question=2).wrong_points == 1


# ---- picture-based questions ----

def test_picture_question_shows_original(db, settings, fake_ai, sasmo_src, child_client, child):
    fake_ai.respond(QuestionAnalysis, lambda call: QuestionAnalysis(
        transcription="Which cube is formed?\n\n[[figure]]", answer_type="mcq", tags=[], picture_based=True))
    p = _import(db, settings, fake_ai, sasmo_src, ["Grade 8 · 2019"])[2019]
    p.published = True
    db.commit()
    q = p.questions[0]
    assert q.show_original is True
    a = start_attempt(db, child, p, "practice", [q.number])
    html = child_client.get(f"/attempts/{a.id}?q={q.number}").text
    assert f'src="/files/{q.crop_paths[0]}"' in html and "Which cube is formed?" not in html


def test_parent_can_toggle_original(parent_client, db, settings, plain_analysis, sasmo_src):
    p = _import(db, settings, plain_analysis, sasmo_src, ["Grade 8 · 2019"])[2019]
    q = p.questions[0]
    assert not q.show_original
    parent_client.post(f"/parent/questions/{q.id}/display", data={"show_original": "on"})
    db.expire_all()
    assert db.get(PaperQuestion, q.id).show_original is True
    parent_client.post(f"/parent/questions/{q.id}/display", data={})
    db.expire_all()
    assert db.get(PaperQuestion, q.id).show_original is False


# ---- practice list ----

def test_practice_lists_newest_year_first(child_client, db, settings, plain_analysis, sasmo_src):
    for p in _import(db, settings, plain_analysis, sasmo_src, ["Grade 8 · 2019", "Grade 8 · 2020"]).values():
        p.published = True
    db.commit()
    html = child_client.get("/practice?contest=SASMO&level=Grade+8").text
    assert html.index("SASMO 2020 Grade 8") < html.index("SASMO 2019 Grade 8")


# ---- answers read exactly from worked solutions ----

def _solutions_pdf(tmp_path):
    import pymupdf as fitz
    doc = fitz.open()
    blocks = [["Solutions to SASMO 2019 Grade 8", "Question 1", "9 + 15 x 134 = 2019", "Answer: (B)",
               "Question 2", "Some working."],
              ["SASMO 2019, Grade 8 Contest Solutions", "Answer: (E)", "Question 16", "Count them all.",
               "Answer: 59", "Question 17", "Answer: -3/4"]]
    for lines in blocks:
        page = doc.new_page()
        for i, t in enumerate(lines):
            page.insert_text((72, 80 + 22 * i), t, fontsize=11)
    path = tmp_path / "sol.pdf"
    doc.save(path)
    return path


def test_answers_from_solution_text(tmp_path):
    from app.importer.solutions import answers_from_solutions
    assert answers_from_solutions(_solutions_pdf(tmp_path), 1, 2) == {1: "B", 2: "E", 16: "59", 17: "-3/4"}


def test_answers_from_solution_text_handles_bad_pages(tmp_path):
    from app.importer.solutions import answers_from_solutions
    assert answers_from_solutions(_solutions_pdf(tmp_path), 5, 9) == {}


def test_import_prefers_exact_solution_answers(db, settings, plain_analysis, sasmo_src, monkeypatch):
    import app.importer.pipeline as pl
    st = two_year_structure()
    st["sections"][0]["solutions_first_page"] = 13
    st["sections"][0]["solutions_last_page"] = 13
    sasmo_src.structure = PdfStructure.model_validate(st).model_dump(mode="json")
    db.commit()
    seen = {}

    def fake(pdf, first, last):
        seen["pages"] = (first, last)
        return {1: "7"}
    monkeypatch.setattr(pl, "answers_from_solutions", fake)
    p = _import(db, settings, plain_analysis, sasmo_src, ["Grade 8 · 2019"])[2019]
    answers = {q.number: q.problem.answer for q in p.questions}
    assert seen["pages"] == (13, 13)
    assert answers[1] == "7"   # exact text answer wins
    assert answers[2] == "19"  # no text answer: Claude's reading is kept


def test_crop_folder_name_is_safe(settings):
    from app.importer.pipeline import crop_dir
    p = Paper(source_pdf_id=3, category="../../etc Secondary 2 (Grade 8)", year=2019)
    d = crop_dir(settings, p)
    assert d.parent == settings.data_dir / "crops" / "3"
    assert d.name == "etc-Secondary-2-Grade-8-2019"
    assert crop_dir(settings, Paper(source_pdf_id=3, category="Junior")).name == "Junior"
