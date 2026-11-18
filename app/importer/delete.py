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


def delete_source(db: Session, settings: Settings, src: SourcePdf) -> None:
    """Delete the PDF, its papers and questions, and any attempts, photos and follow-ups on them.
    Problems also used by another upload's papers are kept."""
    files: list[Path] = [Path(src.path), settings.data_dir / "pages" / str(src.id),
                         settings.data_dir / "crops" / str(src.id)]
    attempts = _attempts(db, src)
    response_ids = [r.id for a in attempts for r in a.responses]
    files += [settings.data_dir / r.photo_path for a in attempts for r in a.responses if r.photo_path]
    if response_ids:
        db.query(UploadToken).filter(UploadToken.response_id.in_(response_ids)).delete(synchronize_session=False)
        db.query(FollowupResponse).filter(FollowupResponse.from_response_id.in_(response_ids)).delete(
            synchronize_session=False)
        db.query(Response).filter(Response.id.in_(response_ids)).delete(synchronize_session=False)
    attempt_ids = [a.id for a in attempts]
    if attempt_ids:
        # redos point at the attempt they redo, so they go first
        db.query(Attempt).filter(Attempt.id.in_(attempt_ids), Attempt.redo_of_id.isnot(None)).delete(
            synchronize_session=False)
        db.query(Attempt).filter(Attempt.id.in_(attempt_ids)).delete(synchronize_session=False)

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
