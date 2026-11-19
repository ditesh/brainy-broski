"""The child's pet collection, choosing a buddy, and the buddy on the home page."""
import re

from app.models import User
from app.pets.creatures import CREATURES
from app.pets.growth import shown_tags
from app.practice.service import save_answer, start_attempt, submit


def _grow(db, child, paper, tag, numbers):
    for n in numbers:
        next(q for q in paper.questions if q.number == n).problem.tags = [tag]
    db.commit()
    a = start_attempt(db, child, paper, "practice", numbers)
    for n in numbers:
        save_answer(db, a, n, next(q for q in paper.questions if q.number == n).problem.answer)
    submit(db, a)


def test_pets_page_for_brand_new_child(child_client, db, child):
    html = child_client.get("/pets").text
    assert "My pets" in html
    assert re.findall(r'data-stage="(\w+)"', html) == []  # no published papers: nothing shown yet
    assert "30 more to discover" in html
    assert child_client.get("/practice").status_code == 200


def test_pets_page_shows_eggs_for_paper_techniques(child_client, db, child, junior_paper):
    html = child_client.get("/pets").text
    shown = shown_tags(db, child)
    stages = re.findall(r'data-stage="(\w+)"', html)
    assert len(stages) == len(shown) and set(stages) == {"egg"}
    assert f"{30 - len(shown)} more to discover" in html
    assert "0 / 2 to hatch" in html


def test_pets_grow_from_answers(child_client, db, child, junior_paper):
    _grow(db, child, junior_paper, "parity", [6, 7, 8])  # 3 × weight 2
    html = child_client.get("/pets").text
    assert 'data-tag="parity" data-stage="baby"' in html and "6 / 15 to grow up" in html


def test_pick_buddy(child_client, db, child, junior_paper):
    _grow(db, child, junior_paper, "parity", [6])
    r = child_client.post("/pets/buddy", data={"tag": "parity"})
    assert r.status_code == 200
    db.expire_all()
    assert db.get(User, child.id).buddy_tag == "parity"
    assert "Your buddy" in r.text


def test_cannot_pick_unhatched_buddy(child_client, junior_paper):
    assert child_client.post("/pets/buddy", data={"tag": "parity"}).status_code == 400
    assert child_client.post("/pets/buddy", data={"tag": "nope"}).status_code == 400


def test_buddy_on_home(child_client, db, child, junior_paper):
    assert 'class="pet-slot' not in child_client.get("/practice").text
    _grow(db, child, junior_paper, "parity", [6])
    html = child_client.get("/practice").text
    assert 'data-tag="parity"' in html and CREATURES["parity"].name in html


def test_pets_tab_for_child_only(child_client, parent_client):
    assert 'href="/pets"' in child_client.get("/practice").text
    assert 'href="/pets"' not in parent_client.get("/parent").text


def test_parent_redirected_to_preview(parent_client):
    r = parent_client.get("/pets", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/parent/pets/preview"


def test_no_pets_on_question_pages(child_client, db, child, junior_paper):
    _grow(db, child, junior_paper, "parity", [6])
    a = start_attempt(db, child, junior_paper, "practice", [1])
    assert 'class="pet-slot' not in child_client.get(f"/attempts/{a.id}?q=1").text
