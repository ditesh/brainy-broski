"""The pet waits in a burrow beside practice questions; tap it and it pops out to help."""
from app.practice.service import save_answer, start_attempt, submit
from app.pets.creatures import CREATURES


def _hatch(db, child, paper):
    q = next(q for q in paper.questions if q.number == 6)
    q.problem.tags = ["parity"]
    db.commit()
    a = start_attempt(db, child, paper, "practice", [6])
    save_answer(db, a, 6, q.problem.answer)
    submit(db, a)


def test_burrow_in_practice(child_client, db, child, junior_paper):
    _hatch(db, child, junior_paper)
    a = start_attempt(db, child, junior_paper, "practice", [1, 2])
    html = child_client.get(f"/attempts/{a.id}?q=1").text
    assert 'class="burrow-box' in html and 'data-tag="parity"' in html and CREATURES["parity"].name in html


def test_no_burrow_in_exam(child_client, db, child, junior_paper):
    _hatch(db, child, junior_paper)
    a = start_attempt(db, child, junior_paper, "contest", [1, 2])
    html = child_client.get(f"/attempts/{a.id}?q=1").text
    assert "burrow-box" not in html and 'class="pet-slot' not in html


def test_burrow_robot_without_buddy(child_client, db, child, junior_paper):
    a = start_attempt(db, child, junior_paper, "practice", [1])
    html = child_client.get(f"/attempts/{a.id}?q=1").text
    assert 'class="burrow-box' in html and "🤖" in html


def test_burrow_has_three_help_buttons(child_client, db, child, junior_paper):
    a = start_attempt(db, child, junior_paper, "practice", [1])
    html = child_client.get(f"/attempts/{a.id}?q=1").text
    for kind in ("hint", "hint2", "solution"):
        assert f'"kind": "{kind}"' in html
    assert f'hx-post="/attempts/{a.id}/help"' in html and "Bye!" in html


def test_pet_pops_out_after_a_right_check(child_client, db, child, junior_paper):
    a = start_attempt(db, child, junior_paper, "practice", [1, 2])
    q1 = next(q for q in junior_paper.questions if q.number == 1)
    html = child_client.post(f"/attempts/{a.id}/check", data={"q": "1", "answer": q1.problem.answer}).text
    assert 'class="burrow-box out' in html


def test_burrow_script_loaded(child_client):
    assert "/static/burrow.js" in child_client.get("/practice").text
