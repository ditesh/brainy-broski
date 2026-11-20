"""A parent can delete a child's finished paper (an attempt), with everything that hangs off it."""
from app.models import Attempt, FollowupResponse, PetBonus, Response, UploadToken, utcnow
from app.pets.growth import growth
from app.practice.service import save_answer, start_attempt, start_redo, submit


def _done(db, child, paper, answers: dict[int, bool]):
    a = start_attempt(db, child, paper, "practice", sorted(answers))
    for n, right in answers.items():
        q = next(x for x in paper.questions if x.number == n)
        save_answer(db, a, n, q.problem.answer if right else "99999")
    submit(db, a)
    return a


def test_history_has_delete_links_for_parent(parent_client, db, child, junior_paper):
    a = _done(db, child, junior_paper, {1: True})
    html = parent_client.get(f"/progress?user={child.id}").text
    assert f'href="/parent/attempts/{a.id}/delete"' in html


def test_child_sees_no_delete_links(child_client, db, child, junior_paper):
    a = _done(db, child, junior_paper, {1: True})
    assert "/delete" not in child_client.get("/progress").text
    assert "/delete" not in child_client.get(f"/attempts/{a.id}/results").text


def test_parent_results_view_links_to_delete(parent_client, db, child, junior_paper):
    a = _done(db, child, junior_paper, {1: True})
    assert f'href="/parent/attempts/{a.id}/delete"' in parent_client.get(f"/attempts/{a.id}/results").text


def test_confirm_page_summarises(parent_client, db, child, junior_paper, settings):
    a = _done(db, child, junior_paper, {1: True, 2: False, 3: False})
    a.responses[1].photo_path = "photos/x.jpg"
    db.commit()
    start_redo(db, a)
    html = parent_client.get(f"/parent/attempts/{a.id}/delete").text
    assert junior_paper.title in html and "3 answers" in html and "1 photo" in html
    assert "1 redo" in html and "pets" in html.lower()
    assert 'action="/parent/attempts/' in html


def test_delete_removes_attempt_and_everything_on_it(parent_client, db, child, junior_paper, settings):
    a = _done(db, child, junior_paper, {6: True, 7: False})
    q6 = next(x for x in junior_paper.questions if x.number == 6)
    q6.problem.tags = ["parity"]
    db.commit()
    photo = settings.data_dir / "photos" / "p.jpg"
    photo.parent.mkdir(parents=True, exist_ok=True)
    photo.write_bytes(b"jpg")
    miss = next(r for r in a.responses if r.correct_first is False)
    miss.photo_path = "photos/p.jpg"
    db.add(UploadToken(token="t1", response_id=miss.id, expires_at=utcnow()))
    db.add(FollowupResponse(user_id=child.id, problem_id=q6.problem_id, from_response_id=miss.id, answer="1",
                            correct=True))
    db.commit()
    redo = start_redo(db, a)
    assert growth(db, child)["parity"].points > 0

    a_id, redo_id, child_id = a.id, redo.id, child.id
    r = parent_client.post(f"/parent/attempts/{a_id}/delete", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/progress?user={child_id}"
    db.expire_all()
    assert db.get(Attempt, a_id) is None and db.get(Attempt, redo_id) is None
    assert db.query(Response).count() == 0 and db.query(UploadToken).count() == 0
    assert db.query(FollowupResponse).count() == 0
    assert not photo.exists()
    assert growth(db, child)["parity"].points == 0


def test_delete_keeps_other_attempts(parent_client, db, child, junior_paper):
    keep = _done(db, child, junior_paper, {1: True})
    gone = _done(db, child, junior_paper, {2: True})
    parent_client.post(f"/parent/attempts/{gone.id}/delete")
    db.expire_all()
    assert db.get(Attempt, keep.id) is not None and len(db.get(Attempt, keep.id).responses) == 1


def test_bonus_eggs_stay(parent_client, db, child, junior_paper):
    from app.goals import week_start
    a = _done(db, child, junior_paper, {1: True})
    db.add(PetBonus(user_id=child.id, tag="parity", amount=2, week_start=week_start(utcnow().date())))
    db.commit()
    parent_client.post(f"/parent/attempts/{a.id}/delete")
    assert db.query(PetBonus).count() == 1


def test_child_cannot_delete(child_client, db, child, junior_paper):
    a = _done(db, child, junior_paper, {1: True})
    assert child_client.post(f"/parent/attempts/{a.id}/delete").status_code == 403
    assert db.get(Attempt, a.id) is not None


def test_delete_unknown_attempt(parent_client):
    assert parent_client.get("/parent/attempts/999/delete").status_code == 404
    assert parent_client.post("/parent/attempts/999/delete").status_code == 404


def test_deleting_an_upload_still_works(parent_client, db, child, junior_paper):
    _done(db, child, junior_paper, {1: True})
    src_id = junior_paper.source_pdf_id
    assert parent_client.post(f"/parent/import/{src_id}/delete", follow_redirects=False).status_code == 303
    assert db.query(Attempt).count() == 0
