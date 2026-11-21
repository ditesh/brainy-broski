from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.answers import is_correct
from app.models import Attempt, DiagnosisStatus, Label, Paper, Response, User, utcnow


def start_attempt(db: Session, user: User, paper: Paper, mode: str, question_numbers: list[int] | None,
                  redo_of: "Attempt | None" = None, timer_on: bool = False) -> Attempt:
    by_number = {q.number: q for q in paper.questions}
    numbers = sorted(by_number) if not question_numbers else sorted(set(question_numbers))
    if not numbers or any(n not in by_number for n in numbers):
        raise ValueError("Those questions aren't in this paper.")
    a = Attempt(user_id=user.id, paper_id=paper.id, mode="contest" if mode == "contest" else "practice",
                question_numbers=numbers, redo_of_id=redo_of.id if redo_of else None,
                timer_on=bool(timer_on and mode != "contest" and paper.duration_min) or None)
    db.add(a)
    db.flush()
    for n in numbers:
        db.add(Response(attempt_id=a.id, paper_question_id=by_number[n].id))
    db.commit()
    db.refresh(a)
    return a


def deadline(attempt: Attempt) -> datetime | None:
    """When the clock runs out: exams, and practice with the timer switched on (which never hands in)."""
    mins = attempt.paper.duration_min
    if not mins or not (attempt.mode == "contest" or attempt.timer_on):
        return None
    return attempt.started_at + timedelta(minutes=mins)


def is_expired(attempt: Attempt) -> bool:
    """Only an exam is handed in when time runs out."""
    d = deadline(attempt)
    return attempt.mode == "contest" and d is not None and utcnow() >= d


def verdict(r: Response) -> str | None:
    """What the practice check said about this question so far (None: not checked)."""
    if r.gave_up:
        return "gave_up"
    if r.correct_first is True and r.checked_at is not None:
        return "right"
    if r.correct_retry is True:
        return "right_second"
    if r.correct_retry is False:
        return "wrong_second"
    if r.solution_seen:
        return "gave_up"
    if r.checked_at is not None and r.correct_first is False:
        return "wrong"
    return None


def response_for(attempt: Attempt, number: int) -> Response:
    for r in attempt.responses:
        if r.paper_question.number == number:
            return r
    raise ValueError("No such question in this attempt.")


def save_answer(db: Session, attempt: Attempt, number: int, raw: str) -> None:
    if attempt.submitted_at is not None:
        raise ValueError("This paper has already been handed in.")
    r = response_for(attempt, number)
    if r.locked or r.checked_at is not None:
        raise ValueError("This answer has been checked already.")
    r.first_answer = raw.strip() or None
    db.commit()


def _practice_response(attempt: Attempt, number: int) -> Response:
    if attempt.mode == "contest":
        raise ValueError("No checking in an exam.")
    if attempt.submitted_at is not None:
        raise ValueError("This paper has already been handed in.")
    return response_for(attempt, number)


def check_answer(db: Session, attempt: Attempt, number: int, raw: str) -> str:
    """Practice: mark this answer now. First check → right/wrong; after a wrong one, a second try →
    right_second/wrong_second (then the answer is shown). Returns which happened."""
    r = _practice_response(attempt, number)
    if r.locked:
        raise ValueError("This question is finished.")
    if not raw.strip():
        raise ValueError("Type an answer first.")
    p = r.paper_question.problem
    if r.checked_at is None:
        r.first_answer = raw.strip()
        r.correct_first = is_correct(raw, p.answer, p.answer_type)
        r.checked_at = utcnow()
        db.commit()
        return "right" if r.correct_first else "wrong"
    _apply_retry(r, raw)
    db.commit()
    return "right_second" if r.correct_retry else "wrong_second"


def give_up(db: Session, attempt: Attempt, number: int, raw: str | None = None) -> Response:
    """Practice: show the answer. A typed, unchecked answer is checked first as his answer; unless it was right,
    the question counts as given up (a miss; a blank give-up loses no points)."""
    r = _practice_response(attempt, number)
    if r.locked:
        return r
    if r.checked_at is None and not (raw and raw.strip()):
        raw = r.first_answer  # a tapped multiple-choice option is already saved
    if raw and raw.strip() and r.checked_at is None:
        if check_answer(db, attempt, number, raw) == "right":
            return r
    r.gave_up = True
    if r.correct_first is None and r.first_answer is None:
        r.correct_first = False
    r.checked_at = r.checked_at or utcnow()
    db.commit()
    return r


def submit(db: Session, attempt: Attempt) -> Attempt:
    if attempt.submitted_at is not None:
        return attempt
    score = max_score = 0
    for r in attempt.responses:
        q = r.paper_question
        max_score += q.points
        if r.gave_up and r.first_answer is None:
            r.correct_first = False  # gave up on a blank: a miss, but blanks never lose points
            continue
        if r.first_answer is None:
            r.correct_first = None
            continue
        r.correct_first = is_correct(r.first_answer, q.problem.answer, q.problem.answer_type)
        if r.correct_first:
            score += q.points
        else:
            score -= q.penalty or 0  # negative marking (e.g. SASMO Section A); blanks never lose points
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
    _apply_retry(response, raw)
    db.commit()
    return response


def _apply_retry(response: Response, raw: str) -> None:
    """The second try (in practice, or on the results page). Right second time = a careless slip, self-corrected."""
    p = response.paper_question.problem
    response.retry_answer = raw.strip()
    response.correct_retry = is_correct(raw, p.answer, p.answer_type)
    if response.correct_retry:
        response.label = Label.careless_self_corrected
        response.diagnosis_status = DiagnosisStatus.done


def misses(attempt: Attempt) -> list[Response]:
    return [r for r in attempt.responses
            if r.correct_first is False and r.correct_retry is not True and not r.helped_out]


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
