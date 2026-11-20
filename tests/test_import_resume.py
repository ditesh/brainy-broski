"""An import that stops partway (server restart, AI error) carries on where it stopped, and never
re-imports a year that is already in."""
import pytest

from app.ai.client import AIError
from app.ai.schemas import PdfStructure, QuestionAnalysis
from app.importer.pipeline import run_import
from app.main import _reset_interrupted_jobs
from app.models import ImportStatus, Paper, PaperQuestion, SourcePdf
from tests.test_sasmo import two_year_structure


def ok(call):
    return QuestionAnalysis(transcription="What is $1+1$?", answer_type="integer", tags=["parity"])


@pytest.fixture
def two_years(db, contest_src):
    contest_src.contest, contest_src.year = "SASMO", 2019
    contest_src.structure = PdfStructure.model_validate(two_year_structure()).model_dump(mode="json")
    db.commit()
    return contest_src


BOTH = ["Grade 8 · 2019", "Grade 8 · 2020"]


def _stop_after(fake_ai, n):
    """Answer n questions, then fail like a dropped connection."""
    fake_ai.add(QuestionAnalysis, *[ok(None)] * n, AIError("connection lost"))
    fake_ai.respond(QuestionAnalysis, ok)
    return fake_ai


def _papers(db, src):
    return {p.year: p for p in db.query(Paper).filter_by(source_pdf_id=src.id).all()}


def test_retry_carries_on_without_redoing_finished_questions(db, settings, fake_ai, two_years):
    _stop_after(fake_ai, 25)                       # 2019 done (20), 2020 stopped after 5
    run_import(two_years.id, BOTH, db, fake_ai, settings)
    assert two_years.status == ImportStatus.failed
    kept = {q.id for q in db.query(PaperQuestion)}
    calls = fake_ai.calls(QuestionAnalysis)

    run_import(two_years.id, BOTH, db, fake_ai, settings)
    assert two_years.status == ImportStatus.done
    db.expire_all()
    papers = _papers(db, two_years)
    assert sorted(papers) == [2019, 2020]
    assert len(papers[2019].questions) == 20 and len(papers[2020].questions) == 20
    assert kept <= {q.id for q in db.query(PaperQuestion)}          # nothing thrown away
    assert fake_ai.calls(QuestionAnalysis) - calls == 15            # only the missing 2020 questions


def test_published_year_is_never_imported_again(db, settings, fake_ai, two_years):
    fake_ai.respond(QuestionAnalysis, ok)
    run_import(two_years.id, ["Grade 8 · 2019"], db, fake_ai, settings)
    p2019 = _papers(db, two_years)[2019]
    p2019.published = True
    db.commit()
    calls = fake_ai.calls(QuestionAnalysis)
    run_import(two_years.id, BOTH, db, fake_ai, settings)
    papers = db.query(Paper).filter_by(source_pdf_id=two_years.id).all()
    assert sorted(p.year for p in papers) == [2019, 2020]
    assert fake_ai.calls(QuestionAnalysis) - calls == 20


def test_retry_button_resumes_the_same_years(parent_client, db, settings, fake_ai, two_years):
    _stop_after(fake_ai, 25)
    r = parent_client.post(f"/parent/import/{two_years.id}", data={"categories": BOTH})
    assert r.status_code == 200
    db.expire_all()
    assert db.get(SourcePdf, two_years.id).status == ImportStatus.failed
    parent_client.post(f"/parent/import/{two_years.id}/retry")
    db.expire_all()
    assert db.get(SourcePdf, two_years.id).status == ImportStatus.done
    assert sorted(p.year for p in db.query(Paper)) == [2019, 2020]
    assert db.query(PaperQuestion).count() == 40


def test_restart_mid_import_keeps_the_queue(db, settings, session_factory, fake_ai, two_years):
    _stop_after(fake_ai, 25)
    run_import(two_years.id, BOTH, db, fake_ai, settings)
    two_years.status = ImportStatus.running            # as if the server died mid-way
    db.commit()
    _reset_interrupted_jobs(session_factory)
    db.expire_all()
    src = db.get(SourcePdf, two_years.id)
    assert src.status == ImportStatus.failed and "where it stopped" in src.error
    assert src.queued == BOTH


def test_choice_form_hides_years_already_in(parent_client, db, settings, fake_ai, two_years):
    fake_ai.respond(QuestionAnalysis, ok)
    run_import(two_years.id, ["Grade 8 · 2019"], db, fake_ai, settings)
    two_years.status = ImportStatus.needs_review
    db.commit()
    html = parent_client.get(f"/parent/import/{two_years.id}", headers={"HX-Request": "1"}).text
    form = html[:html.index("Imported papers")]
    assert 'value="Grade 8 · 2020"' in form and 'value="Grade 8 · 2019"' not in form


def test_queue_cleared_when_done(db, settings, fake_ai, two_years):
    fake_ai.respond(QuestionAnalysis, ok)
    run_import(two_years.id, BOTH, db, fake_ai, settings)
    assert two_years.queued is None
    assert all(p.complete for p in db.query(Paper))
