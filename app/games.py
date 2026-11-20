"""Brain-break games: rounds he earns by answering questions, and the puzzles for each game."""
import random
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from fractions import Fraction
from itertools import permutations, product
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.goals import problems_in
from app.models import GamePlay, User

QUESTIONS_PER_BATCH, ROUNDS_PER_BATCH = 3, 2
TARGET = 24

GAMES = {
    "nim": {"name": "Stone Duel", "emoji": "🪨",
            "blurb": "Take 1, 2 or 3 stones. Whoever takes the last stone wins. Can you beat your buddy?"},
    "target": {"name": "Target 24", "emoji": "🎯",
               "blurb": "Use all four numbers with + − × ÷ to make 24."},
}


@dataclass
class Rounds:
    answered: int   # questions answered today
    left: int       # rounds he can still start today
    to_next: int    # questions until the next batch of rounds


def _today_utc(tz: str) -> tuple[datetime, datetime]:
    z = ZoneInfo(tz)
    today = datetime.now(z).date()
    to_utc = lambda d: datetime.combine(d, time(), z).astimezone(timezone.utc).replace(tzinfo=None)
    return to_utc(today), to_utc(today + timedelta(days=1))


def rounds_left(db: Session, user: User, tz: str) -> Rounds:
    start, end = _today_utc(tz)
    answered = len(problems_in(db, user, start, end))
    used = (db.query(GamePlay).filter(GamePlay.user_id == user.id, GamePlay.started_at >= start,
                                      GamePlay.started_at < end).count())
    earned = answered // QUESTIONS_PER_BATCH * ROUNDS_PER_BATCH
    return Rounds(answered, max(0, earned - used), QUESTIONS_PER_BATCH - answered % QUESTIONS_PER_BATCH)


def record(db: Session, user: User) -> dict:
    plays = db.query(GamePlay).filter(GamePlay.user_id == user.id, GamePlay.won.is_(True)).all()
    return {g: sum(1 for p in plays if p.game == g) for g in GAMES}


# ---- Stone Duel (Nim) ----

def nim_pile(rng: random.Random) -> int:
    return rng.randint(15, 23)


# ---- Target 24 ----

_OPS = {"+": lambda a, b: a + b, "−": lambda a, b: a - b, "×": lambda a, b: a * b,
        "÷": lambda a, b: a / b if b else None}


def solve(numbers: list[int], target: int = TARGET) -> str | None:
    """One way to make target from all the numbers with + − × ÷ (as an expression), or None."""
    def go(items: list[tuple[Fraction, str]]) -> str | None:
        if len(items) == 1:
            return items[0][1] if items[0][0] == target else None
        for i, j in permutations(range(len(items)), 2):
            (a, ea), (b, eb) = items[i], items[j]
            rest = [items[k] for k in range(len(items)) if k not in (i, j)]
            for op, fn in _OPS.items():
                v = fn(a, b)
                if v is None or v < 0:
                    continue
                found = go(rest + [(v, f"({ea} {op} {eb})")])
                if found:
                    return found
        return None
    expr = go([(Fraction(n), str(n)) for n in numbers])
    return expr[1:-1] if expr and expr.startswith("(") else expr


def make_target(rng: random.Random) -> tuple[list[int], int, str]:
    """Four numbers 1-9 that can make 24, the target, and one solution."""
    while True:
        nums = [rng.randint(1, 9) for _ in range(4)]
        answer = solve(nums)
        if answer:
            return nums, TARGET, answer
