"""Reference solutions (verified against the official answer) and diagnosis of misses."""
import logging
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI
from sqlalchemy.orm import Session

from app.ai.client import AIClient, AIError
from app.ai.prompts import DIAGNOSE_SYSTEM, SOLVE_SYSTEM
from app.ai.schemas import Diagnosis, ReferenceSolution
from app.answers import is_correct
from app.config import Settings
from app.models import DiagnosisStatus, Label, Problem, Response
from app.techniques import TECHNIQUES

log = logging.getLogger(__name__)
SOLVE_TRIES = 2


def ensure_reference_solution(db: Session, problem: Problem, crop_paths: list[Path], ai: AIClient) -> bool:
    if problem.verified is not None:
        return bool(problem.verified)
    for _ in range(SOLVE_TRIES):
        try:
            sol = ai.structured(ReferenceSolution, SOLVE_SYSTEM, crop_paths,
                                "Solve this question. Give clear numbered steps.", "high")
        except AIError as e:
            log.warning("reference solve failed for problem %s: %s", problem.id, e)
            return False  # verified stays None: try again later
        if is_correct(sol.final_answer, problem.answer, problem.answer_type):
            problem.reference_solution = "\n".join(f"{i}. {s}" for i, s in enumerate(sol.steps, start=1))
            problem.verified = True
            db.commit()
            return True
    problem.verified = False
    problem.reference_solution = None
    db.commit()
    return False


def _diagnosis_text(r: Response, problem: Problem, has_photo: bool) -> str:
    tags = "\n".join(f"- {t}: {name}" for t, name, _ in TECHNIQUES)
    return (
        f"Official answer: {problem.answer}\n\n"
        f"Checked reference solution:\n{problem.reference_solution}\n\n"
        f"Student's first answer: {r.first_answer}\n"
        f"Student's second answer: {r.retry_answer or '(none)'}\n"
        f"Photo of working: {'attached (the last image)' if has_photo else 'not provided'}\n\n"
        f"Allowed technique tags:\n{tags}"
    )


def diagnose_response(db: Session, response_id: int, ai: AIClient, settings: Settings) -> None:
    try:
        _diagnose(db, response_id, ai, settings)
    except Exception:  # never leave a card spinning forever
        log.exception("diagnosis crashed for response %s", response_id)
        _mark_failed(db, response_id)


def _diagnose(db: Session, response_id: int, ai: AIClient, settings: Settings) -> None:
    r = db.get(Response, response_id)
    if r is None:
        return
    r.diagnosis_status = DiagnosisStatus.pending
    db.commit()
    q = r.paper_question
    problem = q.problem
    crops = [settings.data_dir / p for p in q.crop_paths]
    if not ensure_reference_solution(db, problem, crops, ai):
        r.label = Label.unsure
        r.diagnosis = {"unverified": True}
        r.diagnosis_status = DiagnosisStatus.done if problem.verified is False else DiagnosisStatus.failed
        db.commit()
        return
    images = list(crops)
    has_photo = bool(r.photo_path)
    if has_photo:
        images.append(settings.data_dir / r.photo_path)
    try:
        d = ai.structured(Diagnosis, DIAGNOSE_SYSTEM, images, _diagnosis_text(r, problem, has_photo), "medium")
    except AIError as e:
        log.warning("diagnosis failed for response %s: %s", r.id, e)
        r.label, r.diagnosis_status = Label.unsure, DiagnosisStatus.failed
        db.commit()
        return
    r.diagnosis = d.model_dump()
    r.label = Label(d.label)
    r.diagnosis_status = DiagnosisStatus.done
    db.commit()


def _run(app: FastAPI, response_id: int) -> None:
    db = app.state.session_factory()
    try:
        diagnose_response(db, response_id, app.state.ai, app.state.settings)
    finally:
        db.close()


def _mark_failed(db: Session, response_id: int) -> None:
    db.rollback()
    r = db.get(Response, response_id)
    if r is not None:
        r.label, r.diagnosis_status = Label.unsure, DiagnosisStatus.failed
        db.commit()


def enqueue_diagnosis(background: BackgroundTasks, app: FastAPI, db: Session, response: Response) -> None:
    response.diagnosis_status = DiagnosisStatus.pending
    db.commit()
    background.add_task(_run, app, response.id)
