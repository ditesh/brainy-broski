"""Regression tests for the final-review findings."""
import sqlite3
import threading

import pymupdf as fitz
import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.ai.schemas import QuestionAnalysis
from app.answers import is_correct, normalise
from app.db import make_engine
from app.followups import pick_followups
from app.models import (AnswerType, DiagnosisStatus, ImportStatus, Label, Paper, Response, SourcePdf)
from app.pdf.render import crop_questions, find_anchors
from app.practice.service import save_answer, start_attempt, submit, submit_retry
from tests.conftest import get_pq, login_as
from tests.fixtures.make_pdf import build_contest_pdf


# ---- #1 / #2: follow-ups must not leak answers ----

@pytest.fixture
def tech_response(db, papers, child):
    a = start_attempt(db, child, papers["Junior"], "practice", [2])
    save_answer(db, a, 2, "5")
    submit(db, a)
    r = a.responses[0]
    submit_retry(db, r, "6")
    r.label, r.diagnosis_status = Label.technique, DiagnosisStatus.done
    r.diagnosis = {"label": "technique", "technique_tag": "casework", "hint": "h", "explanation": "e"}
    db.commit()
    return r


def test_followup_rejects_question_not_offered(child_client, db, papers, tech_response):
    other = get_pq(db, papers["Primary"], 12)  # not casework, never offered
    r = child_client.post(f"/responses/{tech_response.id}/followups/{other.id}", data={"answer": "1"})
    assert r.status_code == 404 and other.problem.answer not in r.text


def test_followup_rejected_when_not_technique(child_client, db, papers, tech_response):
    tech_response.label = Label.careless
    db.commit()
    pq = get_pq(db, papers["Junior"], 11)
    assert child_client.post(f"/responses/{tech_response.id}/followups/{pq.id}",
                             data={"answer": "1"}).status_code == 404


def test_followups_exclude_open_attempt_problems(db, child, papers, tech_response):
    start_attempt(db, child, papers["Junior"], "contest", [11, 15, 19, 7])  # open, nothing answered
    picks = pick_followups(db, child, tech_response, "casework", n=10)
    assert all(p.paper.category != "Junior" for p in picks)


# ---- #3: SQLite locking ----

def test_file_engine_uses_wal_and_busy_timeout(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path}/x.db")
    with eng.connect() as c:
        assert c.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert c.execute(text("PRAGMA busy_timeout")).scalar() >= 5000


def test_import_does_not_hold_write_lock_during_ai_calls(tmp_path, settings, fake_ai):
    from app.db import Base
    from app.importer.pipeline import run_import
    from tests.fixtures.make_pdf import contest_layout, contest_structure_dict
    from tests.support.contest import analysis_responder
    dbfile = tmp_path / "lock.db"
    eng = make_engine(f"sqlite:///{dbfile}")
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng, expire_on_commit=False)()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    pdf = build_contest_pdf(settings.data_dir / "c.pdf", contest_layout())
    src = SourcePdf(filename="c", path=str(pdf), contest="X", year=2020, structure=contest_structure_dict(),
                    status=ImportStatus.needs_review)
    db.add(src)
    db.commit()
    blocked = []

    def responder(call):
        con = sqlite3.connect(dbfile, timeout=0.2)
        try:
            con.execute("create table if not exists probe (x int)")
            con.execute("insert into probe values (1)")
            con.commit()
        except sqlite3.OperationalError as e:
            blocked.append(str(e))
        finally:
            con.close()
        return analysis_responder(call)

    fake_ai.respond(QuestionAnalysis, responder)
    run_import(src.id, ["Junior"], db, fake_ai, settings)
    assert blocked == [] and src.status == ImportStatus.done


# ---- #4: stuck jobs are reset at startup ----

def test_startup_resets_stuck_jobs(settings, session_factory, db, papers, child, contest_src):
    contest_src.status = ImportStatus.running
    a = start_attempt(db, child, papers["Junior"], "practice", [1])
    r = a.responses[0]
    r.diagnosis_status = DiagnosisStatus.pending
    db.commit()
    from app.main import create_app
    create_app(settings, session_factory=session_factory)
    db.expire_all()
    assert db.get(SourcePdf, contest_src.id).status == ImportStatus.failed
    assert "interrupted" in db.get(SourcePdf, contest_src.id).error.lower()
    rr = db.get(Response, r.id)
    assert rr.diagnosis_status == DiagnosisStatus.failed and rr.label == Label.unsure


# ---- #5: re-import after the child used the paper ----

def test_reimport_keeps_history_and_finishes(db, settings, fake_ai, papers, child, contest_src):
    from app.importer.pipeline import run_import
    junior = papers["Junior"]
    a = start_attempt(db, child, junior, "practice", [1])
    save_answer(db, a, 1, "18")
    submit(db, a)
    junior.published = False
    db.commit()
    run_import(contest_src.id, ["Junior"], db, fake_ai, settings)
    db.expire_all()
    assert db.get(SourcePdf, contest_src.id).status == ImportStatus.done
    assert db.get(Response, a.responses[0].id).paper_question.problem.answer == "18"
    assert db.query(Paper).filter_by(category="Junior").count() == 1   # carried on with, not copied


# ---- #6: running headers are not continuations; parent can drop an image ----

def _pdf_with_header(path):
    doc = fitz.open()
    for pno, items in enumerate([[("Problem 1.", "First question text.")],
                                 [("Problem 2.", "Second question text.")]], start=1):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 36), "IMONST 2020 - Junior Category (English)", fontsize=9)
        y = 300 if pno == 1 else 120
        for label, body in items:
            page.insert_text((72, y), f"{label} {body}", fontsize=11)
        page.insert_text((290, 800), str(pno), fontsize=10)
    doc.save(str(path))
    return path


def test_running_header_not_a_continuation(tmp_path):
    pdf = _pdf_with_header(tmp_path / "h.pdf")
    crops = crop_questions(pdf, find_anchors(pdf, [1, 2]), tmp_path / "out")
    assert [c.page for c in crops[1]] == [1]


def test_parent_can_drop_extra_image(parent_client, db, imported_paper):
    q = get_pq(db, imported_paper, 2)
    q.crop_paths = q.crop_paths + q.crop_paths
    q.crop_boxes = q.crop_boxes + q.crop_boxes
    db.commit()
    parent_client.post(f"/parent/questions/{q.id}/drop-image", data={"index": "1"})
    db.refresh(q)
    assert len(q.crop_paths) == 1 and len(q.crop_boxes) == 1
    r = parent_client.post(f"/parent/questions/{q.id}/drop-image", data={"index": "0"})
    assert r.status_code == 400  # never remove the last image


# ---- #7: mixed numbers ----

def test_mixed_number_parsed():
    assert normalise("1 1/2", AnswerType.fraction) == "3/2"
    assert is_correct("1 1/2", "3/2", AnswerType.fraction)
    assert is_correct("1.5", "1 1/2", AnswerType.fraction)


# ---- #8: login abuse ----

def test_login_locks_out_after_repeated_failures(client, parent):
    for _ in range(10):
        client.post("/login", data={"username": "dad", "password": "wrong"})
    r = client.post("/login", data={"username": "dad", "password": "pw"}, follow_redirects=False)
    assert r.status_code == 429 and "Too many" in r.text


def test_password_hash_uses_low_memory_profile(db):
    from app.auth import hash_password
    assert "m=19456" in hash_password("x")


def test_unknown_user_still_runs_a_hash(client, monkeypatch):
    import app.auth as auth
    calls = []
    real = auth._ph

    class Spy:
        def verify(self, h, p):
            calls.append(1)
            return real.verify(h, p)

    monkeypatch.setattr(auth, "_ph", Spy())
    client.post("/login", data={"username": "nobody", "password": "x"})
    assert calls


# ---- promoted minor: empty retry must not burn the retry ----

def test_empty_retry_does_not_use_up_retry(db, junior_paper, child):
    a = start_attempt(db, child, junior_paper, "practice", [1])
    save_answer(db, a, 1, "81")
    submit(db, a)
    r = a.responses[0]
    with pytest.raises(ValueError):
        submit_retry(db, r, "   ")
    assert r.retry_answer is None
    assert submit_retry(db, r, "18").correct_retry is True
