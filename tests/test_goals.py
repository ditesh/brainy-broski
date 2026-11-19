"""Weekly goals: setting the target, counting problems per week (local time), and the streak."""
from datetime import date, datetime, timedelta

import pytest

from app.goals import (count_for_week, goal_status, pending_goal, set_goal, streak, target_for, week_start)
from app.models import FollowupResponse, WeeklyGoal
from app.practice.service import save_answer, start_attempt, submit

TZ = "Asia/Kuala_Lumpur"
WED = date(2026, 11, 18)          # a Wednesday
MON = date(2026, 11, 16)


def q(paper, n):
    return next(x for x in paper.questions if x.number == n)


def do_paper(db, child, paper, answers: dict[int, str], when_utc: datetime, submitted=True):
    """answers: question number -> answer ('' = blank, 'R' = right, 'W' = wrong)."""
    a = start_attempt(db, child, paper, "practice", sorted(answers))
    for n, v in answers.items():
        raw = q(paper, n).problem.answer if v == "R" else ("99999" if v == "W" else "")
        save_answer(db, a, n, raw)
    if submitted:
        submit(db, a)
        a.started_at = a.submitted_at = when_utc
        db.commit()
    return a


def at(d: date, hour=4):  # 04:00 UTC = 12:00 in Kuala Lumpur
    return datetime(d.year, d.month, d.day, hour)


def test_week_start():
    assert week_start(WED) == MON and week_start(MON) == MON and week_start(date(2026, 11, 22)) == MON


def test_first_goal_applies_now(db, child):
    set_goal(db, child, 15, today=WED)
    assert target_for(db, child, MON) == 15


def test_later_change_applies_next_week(db, child):
    set_goal(db, child, 15, today=WED)
    set_goal(db, child, 20, today=WED + timedelta(days=1))
    nxt = MON + timedelta(weeks=1)
    assert target_for(db, child, MON) == 15 and target_for(db, child, nxt) == 20
    assert pending_goal(db, child, WED) == 20
    set_goal(db, child, 25, today=WED + timedelta(days=1))
    assert pending_goal(db, child, WED) == 25
    assert db.query(WeeklyGoal).filter_by(user_id=child.id, week_start=nxt).count() == 1


def test_goal_range(db, child):
    for bad in (0, 201):
        with pytest.raises(ValueError):
            set_goal(db, child, bad, today=WED)


def test_counts_distinct_answered_problems(db, child, junior_paper):
    do_paper(db, child, junior_paper, {1: "R", 2: "R", 3: "W", 4: ""}, at(WED))
    do_paper(db, child, junior_paper, {1: "R", 2: "W", 3: "W"}, at(WED + timedelta(days=1)))
    assert count_for_week(db, child, MON, TZ) == 3


def test_followups_count(db, child, junior_paper):
    a = do_paper(db, child, junior_paper, {1: "W"}, at(WED))
    other = q(junior_paper, 5).problem_id
    db.add(FollowupResponse(user_id=child.id, problem_id=other, from_response_id=a.responses[0].id,
                            answer="1", correct=False, created_at=at(WED)))
    db.commit()
    assert count_for_week(db, child, MON, TZ) == 2


def test_unsubmitted_and_blank_do_not_count(db, child, junior_paper):
    do_paper(db, child, junior_paper, {1: "R", 2: "W"}, at(WED), submitted=False)
    do_paper(db, child, junior_paper, {3: ""}, at(WED))
    assert count_for_week(db, child, MON, TZ) == 0


def test_week_boundary_uses_local_time(db, child, junior_paper):
    do_paper(db, child, junior_paper, {1: "R"}, datetime(2026, 11, 22, 15, 30))  # Sun 23:30 local
    do_paper(db, child, junior_paper, {2: "R"}, datetime(2026, 11, 22, 16, 30))  # Mon 00:30 local
    assert count_for_week(db, child, MON, TZ) == 1
    assert count_for_week(db, child, date(2026, 11, 23), TZ) == 1


def _meet(db, child, paper, monday, nums=(1, 2)):
    do_paper(db, child, paper, {n: "R" for n in nums}, at(monday + timedelta(days=1)))


def test_streak(db, child, junior_paper):
    weeks = [MON - timedelta(weeks=k) for k in (4, 3, 2, 1)]
    db.add(WeeklyGoal(user_id=child.id, week_start=weeks[0], target=2))
    db.commit()
    for i, m in enumerate(weeks[1:]):  # met -3, -2, -1; missed -4
        _meet(db, child, junior_paper, m, nums=(2 * i + 1, 2 * i + 2))
    assert streak(db, child, WED, TZ) == 3
    _meet(db, child, junior_paper, MON, nums=(9, 10))
    assert streak(db, child, WED, TZ) == 4


def test_streak_broken_by_missed_last_week(db, child, junior_paper):
    db.add(WeeklyGoal(user_id=child.id, week_start=MON - timedelta(weeks=3), target=2))
    db.commit()
    _meet(db, child, junior_paper, MON - timedelta(weeks=2))
    assert streak(db, child, WED, TZ) == 0
    _meet(db, child, junior_paper, MON, nums=(3, 4))
    assert streak(db, child, WED, TZ) == 1


def test_goal_status(db, child, junior_paper):
    assert goal_status(db, child, WED, TZ).target is None
    set_goal(db, child, 2, today=WED)
    _meet(db, child, junior_paper, MON)
    s = goal_status(db, child, WED, TZ)
    assert (s.target, s.done, s.met, s.streak, s.pending) == (2, 2, True, 1, None)


def test_first_goal_can_be_fixed_the_same_day(db, child):
    set_goal(db, child, 150, today=WED)
    set_goal(db, child, 15, today=WED)
    assert target_for(db, child, MON) == 15 and pending_goal(db, child, WED) is None
