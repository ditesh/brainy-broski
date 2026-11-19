"""Technique pets grow from his answers: weight by difficulty, recovery, follow-ups, bonus eggs."""
from datetime import timedelta

from app.goals import count_for_week, set_goal
from app.models import FollowupResponse, PetBonus, Problem
from app.pets.growth import (GROWN, HATCH, buddy, growth, question_weight, settle_week, shown_tags, stage)
from app.practice.service import submit_retry
from app.techniques import TECHNIQUES
from tests.test_goals import MON, TZ, WED, at, do_paper, q

ALL_TAGS = [t for t, _, _ in TECHNIQUES]


def tag(db, paper, n, *tags):
    q(paper, n).problem.tags = list(tags)
    db.commit()


def test_weight_by_point_rank(junior_paper):
    assert [question_weight(q(junior_paper, n)) for n in (1, 6, 11, 16)] == [1, 2, 3, 3]


def test_single_value_paper_weight_is_two(db, junior_paper):
    for x in junior_paper.questions:
        x.points = 5
    db.commit()
    assert question_weight(q(junior_paper, 1)) == 2


def test_all_tags_present(db, child):
    g = growth(db, child)
    assert set(g) == set(ALL_TAGS) and all(s.points == 0 and s.stage == "egg" for s in g.values())


def test_first_correct_grows_by_weight(db, child, junior_paper):
    tag(db, junior_paper, 16, "parity")
    do_paper(db, child, junior_paper, {16: "R"}, at(WED))
    assert growth(db, child)["parity"].points == 3


def test_wrong_does_not_grow(db, child, junior_paper):
    tag(db, junior_paper, 16, "parity")
    do_paper(db, child, junior_paper, {16: "W"}, at(WED))
    assert growth(db, child)["parity"].points == 0


def test_retry_correct_grows_one(db, child, junior_paper):
    tag(db, junior_paper, 16, "parity")
    a = do_paper(db, child, junior_paper, {16: "W"}, at(WED))
    submit_retry(db, a.responses[0], q(junior_paper, 16).problem.answer)
    assert growth(db, child)["parity"].points == 1


def test_later_correct_after_miss_grows_one_once(db, child, junior_paper):
    tag(db, junior_paper, 16, "parity")
    do_paper(db, child, junior_paper, {16: "W"}, at(WED))
    do_paper(db, child, junior_paper, {16: "R"}, at(WED + timedelta(days=1)))
    do_paper(db, child, junior_paper, {16: "R"}, at(WED + timedelta(days=2)))
    assert growth(db, child)["parity"].points == 1


def test_retake_after_first_correct_adds_nothing(db, child, junior_paper):
    tag(db, junior_paper, 6, "parity")
    do_paper(db, child, junior_paper, {6: "R"}, at(WED))
    do_paper(db, child, junior_paper, {6: "R"}, at(WED + timedelta(days=1)))
    assert growth(db, child)["parity"].points == 2


def test_followup_correct_grows_one(db, child, junior_paper):
    a = do_paper(db, child, junior_paper, {1: "W"}, at(WED))
    p = Problem(answer="1", tags=["pigeonhole"])
    db.add(p)
    db.flush()
    for correct in (False, True, True):  # first correct counts once
        db.add(FollowupResponse(user_id=child.id, problem_id=p.id, from_response_id=a.responses[0].id,
                                answer="1", correct=correct, created_at=at(WED)))
    db.commit()
    assert growth(db, child)["pigeonhole"].points == 1


def test_multi_tag_and_unknown_tags(db, child, junior_paper):
    tag(db, junior_paper, 6, "parity", "pigeonhole", "made-up")
    tag(db, junior_paper, 7)
    do_paper(db, child, junior_paper, {6: "R", 7: "R"}, at(WED))
    g = growth(db, child)
    assert g["parity"].points == 2 and g["pigeonhole"].points == 2 and "made-up" not in g
    assert count_for_week(db, child, MON, TZ) == 2


def test_blank_and_unsubmitted_do_not_grow(db, child, junior_paper):
    tag(db, junior_paper, 6, "parity")
    tag(db, junior_paper, 7, "parity")
    do_paper(db, child, junior_paper, {6: ""}, at(WED))
    do_paper(db, child, junior_paper, {7: "R"}, at(WED), submitted=False)
    assert growth(db, child)["parity"].points == 0


def test_as_of_excludes_later_events(db, child, junior_paper):
    tag(db, junior_paper, 6, "parity")
    tag(db, junior_paper, 7, "parity")
    do_paper(db, child, junior_paper, {6: "R"}, at(WED))
    do_paper(db, child, junior_paper, {7: "R"}, at(WED + timedelta(days=1)))
    assert growth(db, child, as_of=at(WED)).get("parity").points == 2
    assert growth(db, child, as_of=at(WED) - timedelta(seconds=1))["parity"].points == 0
    assert growth(db, child)["parity"].last_grew == at(WED + timedelta(days=1))


def test_stages():
    assert (HATCH, GROWN) == (2, 15)
    assert [stage(n) for n in (0, 1, 2, 14, 15, 40)] == ["egg", "egg", "baby", "baby", "grown", "grown"]


def test_shown_tags_from_published_papers(db, child, papers):
    shown = shown_tags(db, child)
    tags_in_papers = {t for p in papers.values() for x in p.questions for t in x.problem.tags}
    assert set(shown) == tags_in_papers and shown == [t for t in ALL_TAGS if t in shown]


def test_bonus_awarded_once_per_met_week(db, child, junior_paper):
    set_goal(db, child, 2, today=WED)
    do_paper(db, child, junior_paper, {1: "W", 2: "W"}, at(WED))
    b = settle_week(db, child, WED, TZ)
    assert b is not None and b.amount == 2 and b.tag in shown_tags(db, child)
    assert settle_week(db, child, WED, TZ) is None
    assert db.query(PetBonus).count() == 1
    assert growth(db, child)[b.tag].points == 2


def test_no_bonus_when_goal_not_met(db, child, junior_paper):
    set_goal(db, child, 5, today=WED)
    do_paper(db, child, junior_paper, {1: "W"}, at(WED))
    assert settle_week(db, child, WED, TZ) is None


def test_bonus_when_no_eggs_left_goes_to_closest_to_grown(db, child, papers, junior_paper):
    for p in papers.values():
        for x in p.questions:
            x.problem.tags = ["parity"] if x.number % 2 else ["algebra"]
    db.commit()
    do_paper(db, child, junior_paper, {16: "R", 18: "R", 6: "R", 20: "R", 1: "R"}, at(WED))  # algebra 3+3+2+3, parity 1
    set_goal(db, child, 1, today=WED)
    assert settle_week(db, child, WED, TZ).tag == "algebra"


def test_buddy_choice_and_default(db, child, junior_paper):
    tag(db, junior_paper, 6, "parity")
    tag(db, junior_paper, 7, "algebra")
    do_paper(db, child, junior_paper, {6: "R"}, at(WED))
    do_paper(db, child, junior_paper, {7: "R"}, at(WED + timedelta(days=1)))
    g = growth(db, child)
    assert buddy(db, child, g) == "algebra"   # most recent to grow
    child.buddy_tag = "parity"
    assert buddy(db, child, g) == "parity"
    child.buddy_tag = "pigeonhole"            # not hatched: fall back
    assert buddy(db, child, g) == "algebra"


def test_no_buddy_without_hatched_pets(db, child):
    assert buddy(db, child, growth(db, child)) is None


def test_retry_in_a_retake_fixes_a_miss(db, child, junior_paper):
    tag(db, junior_paper, 16, "parity")
    do_paper(db, child, junior_paper, {16: "W"}, at(WED))
    b = do_paper(db, child, junior_paper, {16: "W"}, at(WED + timedelta(days=1)))
    submit_retry(db, b.responses[0], q(junior_paper, 16).problem.answer)
    assert growth(db, child)["parity"].points == 1


def test_settle_survives_a_simultaneous_award(db, child, junior_paper, monkeypatch):
    import app.pets.growth as g
    set_goal(db, child, 1, today=WED)
    do_paper(db, child, junior_paper, {1: "W"}, at(WED))
    db.add(PetBonus(user_id=child.id, tag="parity", amount=2, week_start=MON))   # the other tab won the race
    db.commit()
    monkeypatch.setattr(g, "_bonus_for", lambda db, user, week: None)          # ...after we checked
    assert settle_week(db, child, WED, TZ) is None
    assert db.query(PetBonus).count() == 1


def test_settle_recent_awards_last_week(db, child, junior_paper):
    from app.pets.growth import settle_recent
    from app.models import WeeklyGoal
    db.add(WeeklyGoal(user_id=child.id, week_start=MON - timedelta(weeks=1), target=1))
    db.commit()
    do_paper(db, child, junior_paper, {1: "W"}, at(MON - timedelta(days=3)))
    settle_recent(db, child, WED, TZ)
    assert db.query(PetBonus).filter_by(week_start=MON - timedelta(weeks=1)).count() == 1
