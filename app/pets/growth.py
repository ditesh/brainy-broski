"""How much each technique pet has grown, worked out from his answers (no separate ledger).

Matches technique_table's rule: each problem counts from the first time he answered it.
- right first time: the question's weight (1-3, harder questions more)
- wrong first, then right (retry, redo or retake): 1, once per problem
- a follow-up problem right: 1, once per problem
- bonus eggs from weekly goals: their stored amount
"""
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.goals import goal_status, week_start
from app.models import (Attempt, FollowupResponse, Paper, PaperQuestion, PetBonus, Problem, Response, User)
from app.techniques import TECHNIQUES

TAGS = [t for t, _, _ in TECHNIQUES]
TAG_SET = set(TAGS)
HATCH, GROWN = 2, 15
BONUS = 2


def stage(points: int) -> str:
    return "grown" if points >= GROWN else "baby" if points >= HATCH else "egg"


def question_weight(pq: PaperQuestion) -> int:
    """Rank of the question's points among the distinct point values in its paper: 1, 2, then 3 for the rest."""
    values = sorted({x.points for x in pq.paper.questions})
    if len(values) == 1:
        return 2
    return min(values.index(pq.points) + 1, 3)


@dataclass
class PetState:
    tag: str
    points: int
    stage: str
    last_grew: datetime | None


def _known(tags) -> set[str]:
    return {t for t in (tags or []) if t in TAG_SET}


def growth(db: Session, user: User, as_of: datetime | None = None) -> dict[str, PetState]:
    points: dict[str, int] = defaultdict(int)
    last: dict[str, datetime] = {}

    def add(tags, amount: int, when: datetime) -> None:
        for t in _known(tags):
            points[t] += amount
            last[t] = max(last.get(t, when), when)

    q = db.query(Response).join(Attempt).filter(Attempt.user_id == user.id, Attempt.submitted_at.isnot(None))
    if as_of is not None:
        q = q.filter(Attempt.submitted_at <= as_of)
    by_problem: dict[int, list[Response]] = defaultdict(list)
    for r in q.all():
        if r.correct_first is not None:
            by_problem[r.paper_question.problem_id].append(r)
    for rs in by_problem.values():
        rs.sort(key=lambda r: (r.attempt.submitted_at, r.id))
        first, tags = rs[0], rs[0].paper_question.problem.tags
        if first.correct_first:
            add(tags, question_weight(first.paper_question), first.attempt.submitted_at)
        elif first.correct_retry:
            add(tags, 1, first.attempt.submitted_at)
        else:
            later = next((r for r in rs[1:] if r.correct_first), None)
            if later is not None:
                add(tags, 1, later.attempt.submitted_at)

    fq = db.query(FollowupResponse).filter(FollowupResponse.user_id == user.id, FollowupResponse.correct.is_(True))
    if as_of is not None:
        fq = fq.filter(FollowupResponse.created_at <= as_of)
    seen: set[int] = set()
    for f in fq.order_by(FollowupResponse.created_at, FollowupResponse.id).all():
        if f.problem_id not in seen:
            seen.add(f.problem_id)
            add(db.get(Problem, f.problem_id).tags, 1, f.created_at)

    bq = db.query(PetBonus).filter(PetBonus.user_id == user.id)
    if as_of is not None:
        bq = bq.filter(PetBonus.created_at <= as_of)
    for b in bq.all():
        add([b.tag], b.amount, b.created_at)

    return {t: PetState(t, points[t], stage(points[t]), last.get(t)) for t in TAGS}


def shown_tags(db: Session, user: User, states: dict[str, PetState] | None = None) -> list[str]:
    """Pets he can see: techniques in published papers, plus any that have grown."""
    in_papers: set[str] = set()
    for (tags,) in (db.query(Problem.tags).join(PaperQuestion, PaperQuestion.problem_id == Problem.id)
                    .join(Paper, Paper.id == PaperQuestion.paper_id).filter(Paper.published.is_(True))):
        in_papers |= _known(tags)
    states = states if states is not None else growth(db, user)
    return [t for t in TAGS if t in in_papers or states[t].points > 0]


def settle_week(db: Session, user: User, today: date, tz: str) -> PetBonus | None:
    """Hand out this week's bonus egg if the goal is met and it hasn't been given yet."""
    week = week_start(today)
    if not goal_status(db, user, today, tz).met:
        return None
    if db.query(PetBonus).filter_by(user_id=user.id, week_start=week).count():
        return None
    states = growth(db, user)
    shown = shown_tags(db, user, states) or TAGS
    eggs = [t for t in shown if states[t].points == 0]
    if eggs:
        tag = random.Random(f"{user.id}:{week.isoformat()}").choice(eggs)
    else:
        tag = max(shown, key=lambda t: (states[t].points if states[t].points < GROWN else -1, -shown.index(t)))
    bonus = PetBonus(user_id=user.id, tag=tag, amount=BONUS, week_start=week)
    db.add(bonus)
    db.commit()
    return bonus


def buddy(db: Session, user: User, states: dict[str, PetState]) -> str | None:
    """His chosen buddy if hatched, else the hatched pet that grew most recently."""
    if user.buddy_tag in states and states[user.buddy_tag].stage != "egg":
        return user.buddy_tag
    hatched = [s for s in states.values() if s.stage != "egg" and s.last_grew is not None]
    return max(hatched, key=lambda s: s.last_grew).tag if hatched else None
