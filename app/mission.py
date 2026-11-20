"""Today's mission (one tap to start something worthwhile) and what his buddy says on the home page."""
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.goals import GoalStatus
from app.models import Attempt, Paper, Response, User
from app.pets.creatures import CREATURES
from app.pets.growth import GROWN, HATCH, PetState, growth
from app.techniques import TECHNIQUES

MISSION_SIZE = 3
TECHNIQUE_NAMES = {t: name for t, name, _ in TECHNIQUES}
TAG_ORDER = {t: i for i, (t, _, _) in enumerate(TECHNIQUES)}


@dataclass
class Mission:
    kind: str                       # continue | grow | explore | redo
    title: str
    detail: str
    tag: str | None = None
    paper_id: int | None = None
    numbers: list[int] = field(default_factory=list)
    attempt_id: int | None = None


def _answered(db: Session, user: User) -> set[int]:
    rows = (db.query(Response).join(Attempt)
            .filter(Attempt.user_id == user.id, Attempt.submitted_at.isnot(None)).all())
    return {r.paper_question.problem_id for r in rows if (r.first_answer or "").strip()}


def _to_next_stage(s: PetState) -> int:
    if s.stage == "egg":
        return HATCH - s.points
    if s.stage == "baby":
        return GROWN - s.points
    return 1000  # already grown: only if nothing else is left


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def mission_for(db: Session, user: User, papers: list[Paper] | None = None) -> Mission | None:
    """papers: the ones on screen (his chosen competition and level, newest first). Defaults to all published."""
    in_progress = (db.query(Attempt).filter(Attempt.user_id == user.id, Attempt.submitted_at.is_(None))
                   .order_by(Attempt.started_at.desc()).first())
    if in_progress is not None:
        left = sum(1 for r in in_progress.responses if not (r.first_answer or "").strip())
        return Mission("continue", "Finish what you started",
                       f"{in_progress.paper.title} · {_plural(left, 'question')} left", attempt_id=in_progress.id)

    if papers is None:
        papers = db.query(Paper).filter(Paper.published.is_(True)).order_by(Paper.id).all()
    rank = {p.id: i for i, p in enumerate(papers)}
    answered = _answered(db, user)
    open_qs = [(p, q) for p in papers for q in sorted(p.questions, key=lambda q: q.number)
               if q.problem_id not in answered]
    states = growth(db, user)

    by_tag: dict[str, dict[int, list[int]]] = {}
    for p, q in open_qs:
        for t in q.problem.tags or []:
            if t in states:
                by_tag.setdefault(t, {}).setdefault(p.id, []).append(q.number)
    if by_tag:
        tag = min(by_tag, key=lambda t: (_to_next_stage(states[t]), TAG_ORDER[t]))
        paper_id, numbers = max(by_tag[tag].items(), key=lambda kv: (len(kv[1]), -rank[kv[0]]))
        numbers = numbers[:MISSION_SIZE]
        paper = db.get(Paper, paper_id)
        s, c, gap = states[tag], CREATURES[tag], _to_next_stage(states[tag])
        what = f"{_plural(len(numbers), TECHNIQUE_NAMES[tag].lower() + ' question')} from {paper.title}"
        if s.stage == "egg":
            return Mission("grow", "Hatch a mystery egg 🥚",
                           f"{what} · it's {gap} away from hatching!", tag, paper_id, numbers)
        if s.stage == "baby":
            return Mission("grow", f"Help {c.name} grow up",
                           f"{what} · {c.name} is {gap} away from growing up!", tag, paper_id, numbers)
        return Mission("grow", f"Train {c.name}", what, tag, paper_id, numbers)

    if open_qs:  # questions with no technique tags
        p = open_qs[0][0]
        numbers = [q.number for pp, q in open_qs if pp.id == p.id][:MISSION_SIZE]
        return Mission("explore", "Try something new", f"{_plural(len(numbers), 'question')} from {p.title}",
                       paper_id=p.id, numbers=numbers)

    done = (db.query(Attempt).filter(Attempt.user_id == user.id, Attempt.submitted_at.isnot(None))
            .order_by(Attempt.submitted_at.desc()).all())
    for a in done:
        missed = sum(1 for r in a.responses if r.correct_first is False)
        if missed:
            return Mission("redo", "Fix your misses",
                           f"{_plural(missed, 'question')} you missed in {a.paper.title}", attempt_id=a.id)
    return None


def _greeting(name: str, now: datetime) -> str:
    h = now.hour
    if 5 <= h < 12:
        return f"Good morning, {name}! ☀️"
    if 12 <= h < 17:
        return f"Good afternoon, {name}!"
    if 17 <= h < 22:
        return f"Good evening, {name}! 🌆"
    return f"Still up, {name}? 🌙"


def buddy_lines(user: User, buddy: dict | None, goal: GoalStatus | None, mission: Mission | None,
                now: datetime) -> list[str]:
    """What the buddy says, in order; tapping the buddy moves to the next line."""
    lines = [_greeting(user.display_name, now)]
    if mission is not None:
        lines.append("Today's mission is ready 👇")
    if goal is not None:
        if goal.target is None:
            lines.append("Set a weekly goal — you pick the number!")
        elif goal.met:
            lines.append("Goal smashed this week! 🎉")
        else:
            lines.append(f"{goal.target - goal.done} to go this week!")
        if goal.streak >= 2:
            lines.append(f"{goal.streak} weeks in a row 🔥 Keep it going!")
    if buddy is not None:
        lines.append(buddy["c"].catchphrase)
    return lines
