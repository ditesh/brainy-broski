from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Attempt, FollowupResponse, Label, Problem, Response, Technique, User, utcnow
from app.techniques import TECHNIQUES


def effective_label(r: Response) -> Label | None:
    return r.parent_override or r.label


def _submitted_responses(db: Session, user: User) -> list[Response]:
    return (db.query(Response).join(Attempt)
            .filter(Attempt.user_id == user.id, Attempt.submitted_at.isnot(None)).all())


def paper_history(db: Session, user: User) -> list[dict]:
    attempts = (db.query(Attempt).filter(Attempt.user_id == user.id, Attempt.submitted_at.isnot(None))
                .order_by(Attempt.submitted_at.desc()).all())
    return [{"id": a.id, "date": a.submitted_at.date(), "title": a.paper.title, "score": a.score,
             "max_score": a.max_score, "questions": len(a.question_numbers),
             "minutes": max(1, round((a.submitted_at - a.started_at).total_seconds() / 60))}
            for a in attempts]


def _labelled_misses(db: Session, user: User) -> list[tuple[datetime, Label, Response]]:
    out = []
    for r in _submitted_responses(db, user):
        lab = effective_label(r)
        if r.correct_first is False and lab is not None:
            out.append((r.attempt.started_at, lab, r))
    return out


def miss_breakdown(db: Session, user: User, since: date | None) -> dict[Label, int]:
    c: Counter = Counter()
    for when, lab, _ in _labelled_misses(db, user):
        if since is None or when.date() >= since:
            c[lab] += 1
    return dict(c)


def miss_breakdown_by_week(db: Session, user: User, weeks: int = 8) -> list[tuple[date, dict[Label, int]]]:
    today = utcnow().date()
    this_monday = today - timedelta(days=today.weekday())
    starts = [this_monday - timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]
    buckets: dict[date, Counter] = {s: Counter() for s in starts}
    for when, lab, _ in _labelled_misses(db, user):
        d = when.date()
        monday = d - timedelta(days=d.weekday())
        if monday in buckets:
            buckets[monday][lab] += 1
    return [(s, dict(buckets[s])) for s in starts]


def _tags(problem: Problem, extra: str | None = None) -> set[str]:
    tags = set(problem.tags or [])
    if extra:
        tags.add(extra)
    return tags


def technique_table(db: Session, user: User, recent_days: int = 30) -> list[dict]:
    cutoff = utcnow() - timedelta(days=recent_days)
    stats: dict[str, dict] = defaultdict(lambda: {"attempts": 0, "misses": 0, "recent_misses": 0})
    for r in _submitted_responses(db, user):
        if r.correct_first is None:
            continue
        extra = (r.diagnosis or {}).get("technique_tag") if r.correct_first is False else None
        for t in _tags(r.paper_question.problem, extra):
            s = stats[t]
            s["attempts"] += 1
            if r.correct_first is False:
                s["misses"] += 1
                if r.attempt.started_at >= cutoff:
                    s["recent_misses"] += 1
    for f in db.query(FollowupResponse).filter_by(user_id=user.id).all():
        for t in _tags(db.get(Problem, f.problem_id)):
            s = stats[t]
            s["attempts"] += 1
            if not f.correct:
                s["misses"] += 1
                if f.created_at >= cutoff:
                    s["recent_misses"] += 1
    names = {t: n for t, n, _ in TECHNIQUES}
    names.update({t.tag: t.name for t in db.query(Technique).all()})
    rows = [{"tag": t, "name": names.get(t, t), **s, "flagged": s["recent_misses"] >= 2} for t, s in stats.items()]
    rows.sort(key=lambda r: (not r["flagged"], -r["misses"], r["name"]))
    return rows


def recent_misses(db: Session, user: User, limit: int = 20) -> list[Response]:
    ms = [r for r in _submitted_responses(db, user) if r.correct_first is False]
    ms.sort(key=lambda r: (r.attempt.started_at, r.paper_question.number), reverse=True)
    return ms[:limit]
