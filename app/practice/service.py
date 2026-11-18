from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.answers import is_correct
from app.models import Attempt, DiagnosisStatus, Label, Paper, Response, User, utcnow


def start_attempt(db: Session, user: User, paper: Paper, mode: str, question_numbers: list[int] | None,
                  redo_of: "Attempt | None" = None) -> Attempt:
    by_number = {q.number: q for q in paper.questions}
    numbers = sorted(by_number) if not question_numbers else sorted(set(question_numbers))
    if not numbers or any(n not in by_number for n in numbers):
        raise ValueError("Those questions aren't in this paper.")
    a = Attempt(user_id=user.id, paper_id=paper.id, mode="contest" if mode == "contest" else "practice",
                question_numbers=numbers, redo_of_id=redo_of.id if redo_of else None)
    db.add(a)
    db.flush()
    for n in numbers:
        db.add(Response(attempt_id=a.id, paper_question_id=by_number[n].id))
    db.commit()
    db.refresh(a)
    return a


def deadline(attempt: Attempt) -> datetime | None:
    mins = attempt.paper.duration_min
    if attempt.mode != "contest" or not mins:
        return None
    return attempt.started_at + timedelta(minutes=mins)


def is_expired(attempt: Attempt) -> bool:
    d = deadline(attempt)
    return d is not None and utcnow() >= d


def response_for(attempt: Attempt, number: int) -> Response:
    for r in attempt.responses:
        if r.paper_question.number == number:
            return r
    raise ValueError("No such question in this attempt.")


def save_answer(db: Session, attempt: Attempt, number: int, raw: str) -> None:
    if attempt.submitted_at is not None:
        raise ValueError("This paper has already been handed in.")
    r = response_for(attempt, number)
    r.first_answer = raw.strip() or None
    db.commit()


def submit(db: Session, attempt: Attempt) -> Attempt:
    if attempt.submitted_at is not None:
        return attempt
    score = max_score = 0
    for r in attempt.responses:
        q = r.paper_question
        max_score += q.points
        if r.first_answer is None:
            r.correct_first = None
            continue
        r.correct_first = is_correct(r.first_answer, q.problem.answer, q.problem.answer_type)
        if r.correct_first:
            score += q.points
    attempt.score, attempt.max_score, attempt.submitted_at = score, max_score, utcnow()
    db.commit()
    return attempt


def submit_retry(db: Session, response: Response, raw: str) -> Response:
    if response.attempt.submitted_at is None:
        raise ValueError("Hand in the paper first.")
    if response.correct_first is not False or response.retry_answer is not None:
        raise ValueError("No retry available for this question.")
    if not raw.strip():
        raise ValueError("Type an answer first.")
    p = response.paper_question.problem
    response.retry_answer = raw.strip()
    response.correct_retry = is_correct(raw, p.answer, p.answer_type)
    if response.correct_retry:
        response.label = Label.careless_self_corrected
        response.diagnosis_status = DiagnosisStatus.done
    db.commit()
    return response


def misses(attempt: Attempt) -> list[Response]:
    return [r for r in attempt.responses if r.correct_first is False and r.correct_retry is not True]


def start_redo(db: Session, attempt: Attempt) -> Attempt:
    """A practice attempt with only the questions missed first time (self-corrected ones included).
    Reuses an unfinished redo of the same attempt rather than starting another."""
    open_redo = (db.query(Attempt).filter_by(redo_of_id=attempt.id, user_id=attempt.user_id)
                 .filter(Attempt.submitted_at.is_(None)).first())
    if open_redo is not None:
        return open_redo
    numbers = [r.paper_question.number for r in attempt.responses if r.correct_first is False]
    if attempt.submitted_at is None or not numbers:
        raise ValueError("Nothing to redo here.")
    return start_attempt(db, attempt.user, attempt.paper, "practice", numbers, redo_of=attempt)


RECENT_RETAKE_DAYS = 30


def paper_status(db: Session, user: User) -> dict[int, dict]:
    """Per paper: the latest finished attempt (redos of misses don't count) and how many tries."""
    out: dict[int, dict] = {}
    today = utcnow().date()
    for a in (db.query(Attempt).filter(Attempt.user_id == user.id, Attempt.submitted_at.isnot(None),
                                       Attempt.redo_of_id.is_(None))
              .order_by(Attempt.submitted_at)):
        st = out.setdefault(a.paper_id, {"tries": 0})
        days = (today - a.submitted_at.date()).days
        st.update(tries=st["tries"] + 1, score=a.score, max_score=a.max_score, date=a.submitted_at.date(),
                  days_ago=days, recent=days < RECENT_RETAKE_DAYS, attempt_id=a.id)
    return out
