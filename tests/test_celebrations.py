"""Results celebrate: pets that grew (hatching, growing up), meeting the weekly goal, and personal bests."""
from datetime import timedelta

from app.goals import set_goal
from app.models import PetBonus, utcnow
from app.pets.creatures import CREATURES
from app.practice.service import save_answer, start_attempt, submit


def _q(paper, n):
    return next(q for q in paper.questions if q.number == n)


def _do(db, child, paper, answers, tags=None, ago=None):
    for n, t in (tags or {}).items():
        _q(paper, n).problem.tags = [t]
    db.commit()
    a = start_attempt(db, child, paper, "practice", sorted(answers))
    for n, right in answers.items():
        save_answer(db, a, n, _q(paper, n).problem.answer if right else "99999")
    submit(db, a)
    if ago is not None:
        a.started_at = a.submitted_at = utcnow() - ago
        db.commit()
    return a


def _results(client, a):
    return client.get(f"/attempts/{a.id}/results").text


def test_results_show_pets_that_grew(child_client, db, child, junior_paper):
    a = _do(db, child, junior_paper, {6: True, 7: False}, tags={6: "parity", 7: "algebra"})
    html = _results(child_client, a)
    assert "+2" in html and CREATURES["parity"].name in html
    assert CREATURES["algebra"].name not in html          # wrong answer: no growth shown
    assert 'data-play="hatch"' in html                    # 0 -> 2 points hatches the egg


def test_growing_up_plays_glow(child_client, db, child, junior_paper):
    _do(db, child, junior_paper, {16: True, 17: True, 18: True, 19: True},
        tags={16: "parity", 17: "parity", 18: "parity", 19: "parity"}, ago=timedelta(hours=2))   # 12 points
    a = _do(db, child, junior_paper, {11: True}, tags={11: "parity"})                            # +3 = 15
    html = _results(child_client, a)
    assert 'data-play="grow"' in html and 'data-sound="fanfare"' in html


def test_plain_growth_plays_happy(child_client, db, child, junior_paper):
    _do(db, child, junior_paper, {6: True}, tags={6: "parity"}, ago=timedelta(hours=2))
    a = _do(db, child, junior_paper, {7: True}, tags={7: "parity"})
    html = _results(child_client, a)
    assert 'data-play="happy"' in html and 'data-sound="ding"' in html


def test_goal_met_celebration_and_bonus_egg(app, child_client, db, child, junior_paper):
    from app.daily import local_today
    set_goal(db, child, 2, local_today(app.state.settings.timezone))
    a = _do(db, child, junior_paper, {1: False, 2: False})
    html = _results(child_client, a)
    assert "Goal smashed" in html and 'data-sound="jingle"' in html
    bonus = db.query(PetBonus).one()
    assert "Bonus egg" in html and CREATURES[bonus.tag].name in html


def test_no_goal_celebration_when_already_met(app, child_client, db, child, junior_paper):
    from app.daily import local_today
    set_goal(db, child, 1, local_today(app.state.settings.timezone))
    _do(db, child, junior_paper, {1: False}, ago=timedelta(minutes=30))
    a = _do(db, child, junior_paper, {2: False})
    assert "Goal smashed" not in _results(child_client, a)


def test_reopening_results_awards_once(app, child_client, parent_client, db, child, junior_paper):
    from app.daily import local_today
    set_goal(db, child, 2, local_today(app.state.settings.timezone))
    a = _do(db, child, junior_paper, {6: True, 7: True}, tags={6: "parity", 7: "parity"})
    first = _results(child_client, a)
    second = _results(child_client, a)
    parent_client.get(f"/attempts/{a.id}/results")
    assert db.query(PetBonus).count() == 1
    assert CREATURES["parity"].name in first and CREATURES["parity"].name in second
    assert second.count("Bonus egg") == 1


def test_beat_best_confetti(child_client, db, child, junior_paper):
    first = _do(db, child, junior_paper, {1: True, 2: False, 3: False}, ago=timedelta(days=1))
    assert "data-confetti" not in _results(child_client, first)
    same = _do(db, child, junior_paper, {1: True, 2: False, 3: False}, ago=timedelta(hours=5))
    assert "data-confetti" not in _results(child_client, same)
    better = _do(db, child, junior_paper, {1: True, 2: True, 3: False})
    html = _results(child_client, better)
    assert "data-confetti" in html and "new best" in html.lower()


def test_part_attempts_not_compared_with_whole_paper(child_client, db, child, junior_paper):
    _do(db, child, junior_paper, {1: False, 2: False, 3: False, 4: False}, ago=timedelta(days=1))
    a = _do(db, child, junior_paper, {1: True})
    assert "new best" not in _results(child_client, a).lower()


def test_parent_view_has_no_celebration_sounds(parent_client, db, child, junior_paper):
    a = _do(db, child, junior_paper, {6: True}, tags={6: "parity"})
    html = parent_client.get(f"/attempts/{a.id}/results").text
    assert 'data-sound="' not in html and 'data-play="' not in html


def test_egg_that_grew_stays_a_mystery(child_client, db, child, junior_paper):
    a = _do(db, child, junior_paper, {1: True}, tags={1: "parity"})   # weight 1: still an egg
    html = _results(child_client, a)
    assert "+1" in html and "Mystery egg" in html and CREATURES["parity"].name not in html
