"""A child's weekly goal: problems answered per week (Monday–Sunday, local time), and the streak of met weeks."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models import Attempt, FollowupResponse, Response, User, WeeklyGoal

GOAL_MIN, GOAL_MAX = 1, 200


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def local_date(dt_utc: datetime, tz: str) -> date:
    return dt_utc.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz)).date()


def _utc_bounds(week: date, tz: str) -> tuple[datetime, datetime]:
    """The week's local Monday 00:00 to next Monday 00:00, as naive UTC (how the DB stores times)."""
    z = ZoneInfo(tz)
    to_utc = lambda d: datetime.combine(d, time(), z).astimezone(timezone.utc).replace(tzinfo=None)
    return to_utc(week), to_utc(week + timedelta(weeks=1))


def target_for(db: Session, user: User, week: date) -> int | None:
    row = (db.query(WeeklyGoal).filter(WeeklyGoal.user_id == user.id, WeeklyGoal.week_start <= week)
           .order_by(WeeklyGoal.week_start.desc()).first())
    return row.target if row else None


def set_goal(db: Session, user: User, target: int, today: date) -> WeeklyGoal:
    """The first goal starts this week; a change starts next Monday, so it can't be lowered at the last minute."""
    if not GOAL_MIN <= target <= GOAL_MAX:
        raise ValueError(f"goal must be {GOAL_MIN}-{GOAL_MAX}")
    rows = db.query(WeeklyGoal).filter_by(user_id=user.id).all()
    this = week_start(today)
    first_today = len(rows) == 1 and rows[0].week_start == this and rows[0].set_on == today
    # the very first goal starts now, and can be fixed the same day (typed 150 meaning 15)
    start = this if not rows or first_today else this + timedelta(weeks=1)
    row = next((r for r in rows if r.week_start == start), None)
    if row is None:
        row = WeeklyGoal(user_id=user.id, week_start=start, target=target)
        db.add(row)
    row.target, row.set_on = target, today
    db.commit()
    return row


def pending_goal(db: Session, user: User, today: date) -> int | None:
    row = db.query(WeeklyGoal).filter_by(user_id=user.id, week_start=week_start(today) + timedelta(weeks=1)).one_or_none()
    return row.target if row else None


def problems_in(db: Session, user: User, start_utc: datetime, end_utc: datetime) -> set[int]:
    """Distinct problems he gave a real answer to between two UTC times (submitted papers and follow-ups)."""
    rows = (db.query(Response).join(Attempt)
            .filter(Attempt.user_id == user.id, Attempt.submitted_at >= start_utc, Attempt.submitted_at < end_utc)
            .all())
    seen = {r.paper_question.problem_id for r in rows if (r.first_answer or "").strip()}
    seen |= {f.problem_id for f in db.query(FollowupResponse)
             .filter(FollowupResponse.user_id == user.id, FollowupResponse.created_at >= start_utc,
                     FollowupResponse.created_at < end_utc)}
    return seen


def count_for_week(db: Session, user: User, week: date, tz: str) -> int:
    return len(problems_in(db, user, *_utc_bounds(week, tz)))


def _met(db: Session, user: User, week: date, tz: str) -> bool:
    target = target_for(db, user, week)
    return target is not None and count_for_week(db, user, week, tz) >= target


def streak(db: Session, user: User, today: date, tz: str) -> int:
    """Met weeks in a row up to last week, plus this week once it's met."""
    this = week_start(today)
    n, week = 0, this - timedelta(weeks=1)
    while _met(db, user, week, tz):
        n += 1
        week -= timedelta(weeks=1)
    return n + (1 if _met(db, user, this, tz) else 0)


@dataclass
class GoalStatus:
    target: int | None
    done: int
    met: bool
    streak: int
    pending: int | None


def goal_status(db: Session, user: User, today: date, tz: str) -> GoalStatus:
    week = week_start(today)
    target = target_for(db, user, week)
    done = count_for_week(db, user, week, tz)
    return GoalStatus(target=target, done=done, met=target is not None and done >= target,
                      streak=streak(db, user, today, tz) if target else 0, pending=pending_goal(db, user, today))
