"""Brain-break games: earned by answering questions, two maths games, results recorded once."""
import random
import re
from fractions import Fraction

import pytest

from app.games import ROUNDS_PER_BATCH, QUESTIONS_PER_BATCH, make_target, nim_pile, rounds_left, solve
from app.models import GamePlay
from app.practice.service import save_answer, start_attempt, submit


def _answer(db, child, paper, numbers):
    a = start_attempt(db, child, paper, "practice", numbers)
    for n in numbers:
        save_answer(db, a, n, "1")
    submit(db, a)


def _eval(expr: str) -> Fraction:
    return eval(re.sub(r"(\d+)", r"Fraction(\1)", expr.replace("×", "*").replace("÷", "/").replace("−", "-")))


# ---- earning rounds ----

def test_no_rounds_before_answering(db, child, settings):
    assert rounds_left(db, child, settings.timezone).left == 0


def test_three_questions_earn_two_rounds(db, child, settings, junior_paper):
    assert (QUESTIONS_PER_BATCH, ROUNDS_PER_BATCH) == (3, 2)
    _answer(db, child, junior_paper, [1, 2])
    r = rounds_left(db, child, settings.timezone)
    assert r.left == 0 and r.to_next == 1
    _answer(db, child, junior_paper, [3])
    assert rounds_left(db, child, settings.timezone).left == 2


def test_started_rounds_are_used_up(db, child, settings, junior_paper):
    _answer(db, child, junior_paper, [1, 2, 3])
    db.add(GamePlay(user_id=child.id, game="nim"))
    db.commit()
    assert rounds_left(db, child, settings.timezone).left == 1


# ---- puzzles ----

def test_solver_finds_24():
    expr = solve([4, 7, 8, 8], 24)
    assert expr is not None and _eval(expr) == 24
    assert solve([1, 1, 1, 1], 24) is None


def test_target_puzzles_always_solvable():
    rng = random.Random(1)
    for _ in range(30):
        nums, target, answer = make_target(rng)
        assert len(nums) == 4 and all(1 <= n <= 9 for n in nums) and target == 24
        assert _eval(answer) == 24 and sorted(map(int, re.findall(r"\d+", answer))) == sorted(nums)


def test_nim_pile_in_range():
    rng = random.Random(2)
    assert all(15 <= nim_pile(rng) <= 23 for _ in range(50))


# ---- web ----

def test_home_shows_how_many_to_unlock(child_client, db, child, junior_paper):
    html = child_client.get("/practice").text
    assert "Brain break" in html and "3 more questions" in html


def test_home_shows_rounds_when_earned(child_client, db, child, junior_paper):
    _answer(db, child, junior_paper, [1, 2, 3])
    html = child_client.get("/practice").text
    assert "2 games to play" in html and 'href="/games"' in html


def test_games_page_lists_games(child_client, db, child, junior_paper):
    html = child_client.get("/games").text
    assert "Stone Duel" in html and "Target 24" in html


def test_cannot_start_without_rounds(child_client, db, child):
    r = child_client.post("/games/nim/play", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/games"
    assert db.query(GamePlay).count() == 0


def test_start_round_uses_it_and_opens_game(child_client, db, child, settings, junior_paper):
    _answer(db, child, junior_paper, [1, 2, 3])
    r = child_client.post("/games/nim/play", follow_redirects=False)
    play = db.query(GamePlay).one()
    assert r.status_code == 303 and r.headers["location"] == f"/games/nim/{play.id}"
    html = child_client.get(r.headers["location"]).text
    assert 'data-game="nim"' in html and re.search(r'data-pile="(\d+)"', html)
    assert rounds_left(db, child, settings.timezone).left == 1


def test_target_page_has_puzzle(child_client, db, child, junior_paper):
    _answer(db, child, junior_paper, [1, 2, 3])
    loc = child_client.post("/games/target/play", follow_redirects=False).headers["location"]
    html = child_client.get(loc).text
    nums = re.search(r"data-numbers='([^']*)'", html).group(1)
    assert len(re.findall(r"\d", nums)) == 4 and 'data-target="24"' in html


def test_unknown_game(child_client, db, child, junior_paper):
    _answer(db, child, junior_paper, [1, 2, 3])
    assert child_client.post("/games/chess/play").status_code == 404


def test_result_recorded_once(child_client, db, child, junior_paper):
    _answer(db, child, junior_paper, [1, 2, 3])
    loc = child_client.post("/games/nim/play", follow_redirects=False).headers["location"]
    pid = int(loc.rsplit("/", 1)[1])
    assert child_client.post(f"/games/plays/{pid}/result", data={"won": "1"}).status_code == 204
    assert child_client.post(f"/games/plays/{pid}/result", data={"won": "0"}).status_code == 409
    db.expire_all()
    assert db.get(GamePlay, pid).won is True
    assert "1 win" in child_client.get("/games").text


def test_cannot_open_someone_elses_round(child_client, parent, db, child, junior_paper):
    play = GamePlay(user_id=parent.id, game="nim")
    db.add(play)
    db.commit()
    assert child_client.get(f"/games/nim/{play.id}").status_code == 404
    assert child_client.post(f"/games/plays/{play.id}/result", data={"won": "1"}).status_code == 404


def test_parent_can_preview_without_rounds(parent_client, db):
    html = parent_client.get("/games/nim/preview").text
    assert 'data-game="nim"' in html and 'data-round=""' in html
    assert db.query(GamePlay).count() == 0
    assert parent_client.get("/games/target/preview").status_code == 200


def test_child_cannot_use_preview(child_client):
    assert child_client.get("/games/nim/preview").status_code == 403


def test_parent_home_has_no_brain_break(parent_client):
    assert "Brain break" not in parent_client.get("/practice").text
