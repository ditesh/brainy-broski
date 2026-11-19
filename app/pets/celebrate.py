"""What to celebrate on a results page: pets that grew from this paper, a weekly goal just met, a new best."""
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.goals import _utc_bounds, local_date, problems_in, target_for, week_start
from app.models import Attempt, PetBonus, User
from app.pets.growth import growth, settle_week

TICK = timedelta(microseconds=1)


@dataclass
class Grew:
    tag: str
    gained: int
    before: str   # stage before this paper
    after: str    # stage after

    @property
    def play(self) -> str:
        if self.before == "egg" and self.after != "egg":
            return "hatch"
        if self.after == "grown" and self.before != "grown":
            return "grow"
        return "happy"

    @property
    def sound(self) -> str:
        return {"hatch": "crack", "grow": "fanfare"}.get(self.play, "ding")


@dataclass
class Celebration:
    grew: list[Grew] = field(default_factory=list)
    goal_met_now: bool = False
    bonus: PetBonus | None = None
    beat_best: bool = False
    bonus_stage: str = "baby"   # the bonus pet's stage now

    @property
    def any(self) -> bool:
        return bool(self.grew or self.goal_met_now or self.beat_best)


def _beat_best(db: Session, a: Attempt) -> bool:
    """A higher score than every earlier try at exactly the same questions (redos aren't comparable)."""
    if a.redo_of_id is not None:
        return False
    earlier = [x for x in db.query(Attempt).filter(Attempt.user_id == a.user_id, Attempt.paper_id == a.paper_id,
                                                    Attempt.submitted_at.isnot(None), Attempt.redo_of_id.is_(None),
                                                    Attempt.id != a.id).all()
               if x.submitted_at < a.submitted_at and sorted(x.question_numbers) == sorted(a.question_numbers)]
    return bool(earlier) and a.score > max(x.score for x in earlier)


def celebration(db: Session, user: User, a: Attempt, today: date, tz: str) -> Celebration:
    if a.user_id != user.id or a.submitted_at is None:
        return Celebration()
    before, after = growth(db, user, as_of=a.submitted_at - TICK), growth(db, user, as_of=a.submitted_at)
    grew = [Grew(t, after[t].points - before[t].points, before[t].stage, after[t].stage)
            for t in after if after[t].points > before[t].points]
    grew.sort(key=lambda g: ({"grow": 0, "hatch": 1, "happy": 2}[g.play], -g.gained))

    week = week_start(local_date(a.submitted_at, tz))
    target = target_for(db, user, week)
    met_now = False
    if target is not None:
        start, _ = _utc_bounds(week, tz)
        n_before = len(problems_in(db, user, start, a.submitted_at))
        n_after = len(problems_in(db, user, start, a.submitted_at + TICK))
        met_now = n_before < target <= n_after
    bonus = None
    if met_now:
        if week == week_start(today):
            settle_week(db, user, today, tz)
        bonus = db.query(PetBonus).filter_by(user_id=user.id, week_start=week).one_or_none()
    bonus_stage = growth(db, user)[bonus.tag].stage if bonus else "baby"
    return Celebration(grew=grew, goal_met_now=met_now, bonus=bonus, beat_best=_beat_best(db, a),
                       bonus_stage=bonus_stage)
