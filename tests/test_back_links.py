"""Every inner page has a back link to the page above it."""
import re

from app.practice.service import save_answer, start_attempt, submit


def back_href(html):
    m = re.search(r'<a class="back" href="([^"]+)"', html)
    return m and m.group(1)


def _missed(db, child, paper):
    a = start_attempt(db, child, paper, "practice", [2])
    save_answer(db, a, 2, "99")
    submit(db, a)
    return a


def test_child_pages(child_client, db, child, junior_paper):
    a = _missed(db, child, junior_paper)
    r = a.responses[0]
    assert back_href(child_client.get(f"/attempts/{a.id}/results").text) == "/practice"
    assert back_href(child_client.get(f"/attempts/{a.id}/feedback").text) == f"/attempts/{a.id}/results"
    assert back_href(child_client.get(f"/responses/{r.id}/feedback").text) == f"/attempts/{a.id}/results"
    from app.practice.service import submit_retry
    submit_retry(db, r, "98")
    assert back_href(child_client.get(f"/responses/{r.id}/photo").text) == f"/attempts/{a.id}/results"
    a2 = start_attempt(db, child, junior_paper, "practice", [1])
    assert back_href(child_client.get(f"/attempts/{a2.id}?q=1").text) == "/practice"
    assert back_href(child_client.get("/practice").text) is None


def test_parent_viewing_results_goes_back_to_progress(parent_client, db, child, junior_paper):
    a = _missed(db, child, junior_paper)
    assert back_href(parent_client.get(f"/attempts/{a.id}/results").text).startswith("/progress")


def test_parent_pages(parent_client, db, contest_src, junior_paper):
    assert back_href(parent_client.get("/parent/import").text) == "/parent"
    assert back_href(parent_client.get(f"/parent/import/{contest_src.id}").text) == "/parent"
    assert back_href(parent_client.get(f"/parent/import/{contest_src.id}/delete").text) == "/parent"
    assert (back_href(parent_client.get(f"/parent/papers/{junior_paper.id}/review").text)
            == f"/parent/import/{contest_src.id}")
    assert back_href(parent_client.get("/parent").text) is None
