import random
from datetime import timedelta

from sqlalchemy.orm import Session

from app.answers import is_correct
from app.models import Attempt, FollowupResponse, Paper, PaperQuestion, Response, User, utcnow

RECENT_DAYS = 30


def _recently_answered(db: Session, user: User) -> set[int]:
    cutoff = utcnow() - timedelta(days=RECENT_DAYS)
    attempted = (db.query(PaperQuestion.problem_id).join(Response, Response.paper_question_id == PaperQuestion.id)
                 .join(Attempt).filter(Attempt.user_id == user.id, Attempt.started_at >= cutoff,
                                       Response.first_answer.isnot(None)).all())
    followed = (db.query(FollowupResponse.problem_id)
                .filter(FollowupResponse.user_id == user.id, FollowupResponse.created_at >= cutoff).all())
    return {pid for (pid,) in attempted} | {pid for (pid,) in followed}


def pick_followups(db: Session, user: User, response: Response, tag: str, n: int = 2) -> list[PaperQuestion]:
    missed = response.paper_question
    skip = _recently_answered(db, user) | {missed.problem_id}
    candidates = (db.query(PaperQuestion).join(Paper).filter(Paper.published.is_(True))
                  .order_by(PaperQuestion.id).all())
    by_problem: dict[int, PaperQuestion] = {}
    for q in candidates:
        if tag not in (q.problem.tags or []) or q.problem_id in skip:
            continue
        current = by_problem.get(q.problem_id)
        if current is None or (current.paper.category != missed.paper.category
                               and q.paper.category == missed.paper.category):
            by_problem[q.problem_id] = q
    pool = list(by_problem.values())
    random.Random(response.id).shuffle(pool)
    pool.sort(key=lambda q: q.paper.category != missed.paper.category)  # stable: same category first
    return pool[:n]


def followups_for_card(db: Session, user: User, response: Response, tag: str, n: int = 2) -> list[dict]:
    """Already-answered follow-ups from this response first, then fresh picks up to n."""
    done = (db.query(FollowupResponse).filter_by(user_id=user.id, from_response_id=response.id)
            .order_by(FollowupResponse.id).all())
    items: list[dict] = []
    seen: set[int] = set()
    for f in done:
        if f.problem_id in seen:
            continue
        pq = (db.query(PaperQuestion).join(Paper).filter(PaperQuestion.problem_id == f.problem_id)
              .order_by((Paper.category != response.paper_question.paper.category), PaperQuestion.id).first())
        if pq:
            items.append({"pq": pq, "done": f})
            seen.add(f.problem_id)
    if len(items) < n:
        for pq in pick_followups(db, user, response, tag, n=n + len(items)):
            if pq.problem_id not in seen and len(items) < n:
                items.append({"pq": pq, "done": None})
                seen.add(pq.problem_id)
    return items


def answer_followup(db: Session, user: User, response: Response, pq: PaperQuestion, raw: str) -> FollowupResponse:
    p = pq.problem
    f = FollowupResponse(user_id=user.id, problem_id=p.id, from_response_id=response.id, answer=raw.strip(),
                         correct=is_correct(raw, p.answer, p.answer_type))
    db.add(f)
    db.commit()
    return f
