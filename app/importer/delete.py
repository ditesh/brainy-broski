"""Deleting an uploaded PDF and everything that hangs off it."""
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Settings
from app.models import (Attempt, FollowupResponse, Paper, PaperQuestion, Problem, Response, SourcePdf,
                        UploadToken)


def _attempts(db: Session, src: SourcePdf) -> list[Attempt]:
    paper_ids = [p.id for p in src.papers]
    return db.query(Attempt).filter(Attempt.paper_id.in_(paper_ids)).all() if paper_ids else []


def deletion_summary(db: Session, src: SourcePdf) -> dict:
    attempts = _attempts(db, src)
    responses = [r for a in attempts for r in a.responses]
    return {"papers": sorted(p.category for p in src.papers),
            "attempts": len(attempts),
            "photos": sum(1 for r in responses if r.photo_path),
            "children": sorted({a.user.display_name for a in attempts})}


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def delete_attempt_rows(db: Session, settings: Settings, attempts: list[Attempt]) -> list[Path]:
    """Delete these attempts with their answers, upload links and follow-ups. Returns photo files to remove
    once the transaction commits."""
    responses = [r for a in attempts for r in a.responses]
    response_ids = [r.id for r in responses]
    files = [settings.data_dir / r.photo_path for r in responses if r.photo_path]
    if response_ids:
        db.query(UploadToken).filter(UploadToken.response_id.in_(response_ids)).delete(synchronize_session=False)
        db.query(FollowupResponse).filter(FollowupResponse.from_response_id.in_(response_ids)).delete(
            synchronize_session=False)
        db.query(Response).filter(Response.id.in_(response_ids)).delete(synchronize_session=False)
    attempt_ids = [a.id for a in attempts]
    if attempt_ids:
        # redos point at the attempt they redo (possibly in a chain): unlink first, then delete
        db.query(Attempt).filter(Attempt.id.in_(attempt_ids)).update({Attempt.redo_of_id: None},
                                                                     synchronize_session=False)
        db.query(Attempt).filter(Attempt.id.in_(attempt_ids)).delete(synchronize_session=False)
    return files


def with_redos(db: Session, attempt: Attempt) -> list[Attempt]:
    """The attempt plus every "redo my misses" built on it, however deep."""
    out, frontier = [attempt], [attempt.id]
    while frontier:
        found = db.query(Attempt).filter(Attempt.redo_of_id.in_(frontier)).all()
        out += found
        frontier = [a.id for a in found]
    return out


def attempt_deletion_summary(db: Session, attempt: Attempt) -> dict:
    group = with_redos(db, attempt)
    responses = [r for a in group for r in a.responses]
    return {"answers": sum(1 for r in attempt.responses if (r.first_answer or "").strip()),
            "photos": sum(1 for r in responses if r.photo_path), "redos": len(group) - 1}


def delete_attempt(db: Session, settings: Settings, attempt: Attempt) -> None:
    files = delete_attempt_rows(db, settings, with_redos(db, attempt))
    db.commit()
    db.expire_all()
    for f in files:
        _remove(f)


def delete_source(db: Session, settings: Settings, src: SourcePdf) -> None:
    """Delete the PDF, its papers and questions, and any attempts, photos and follow-ups on them.
    Problems also used by another upload's papers are kept."""
    files: list[Path] = [Path(src.path), settings.data_dir / "pages" / str(src.id),
                         settings.data_dir / "crops" / str(src.id)]
    files += delete_attempt_rows(db, settings, _attempts(db, src))

    paper_ids = [p.id for p in src.papers]
    problem_ids = {pid for (pid,) in db.query(PaperQuestion.problem_id).filter(PaperQuestion.paper_id.in_(paper_ids))}
    db.query(PaperQuestion).filter(PaperQuestion.paper_id.in_(paper_ids)).delete(synchronize_session=False)
    db.query(Paper).filter(Paper.id.in_(paper_ids)).delete(synchronize_session=False)
    db.flush()
    still_used = {pid for (pid,) in db.query(PaperQuestion.problem_id).filter(PaperQuestion.problem_id.in_(problem_ids))}
    orphans = problem_ids - still_used
    if orphans:
        db.query(FollowupResponse).filter(FollowupResponse.problem_id.in_(orphans)).delete(synchronize_session=False)
        db.query(Problem).filter(Problem.id.in_(orphans)).delete(synchronize_session=False)
    db.query(SourcePdf).filter(SourcePdf.id == src.id).delete(synchronize_session=False)
    db.commit()
    db.expire_all()
    for f in files:
        _remove(f)
