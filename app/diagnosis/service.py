"""Diagnosis of missed questions. (Filled in by Task 10.)"""
from fastapi import BackgroundTasks, FastAPI
from sqlalchemy.orm import Session

from app.models import DiagnosisStatus, Response


def diagnose_response(db: Session, response_id: int, ai) -> None:  # replaced in Task 10
    return None


def _run(app: FastAPI, response_id: int) -> None:
    db = app.state.session_factory()
    try:
        diagnose_response(db, response_id, app.state.ai)
    finally:
        db.close()


def enqueue_diagnosis(background: BackgroundTasks, app: FastAPI, db: Session, response: Response) -> None:
    response.diagnosis_status = DiagnosisStatus.pending
    db.commit()
    background.add_task(_run, app, response.id)
