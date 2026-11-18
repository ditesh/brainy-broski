import io

import pytest
from PIL import Image

from app.ai.client import AIError, AIRefusal
from app.ai.schemas import Diagnosis, ReferenceSolution
from app.diagnosis.service import diagnose_response, ensure_reference_solution
from app.models import DiagnosisStatus, Label
from app.practice.service import save_answer, start_attempt, submit, submit_retry
from app.uploads import store_photo


def _miss(db, paper, user, n=2, first="5", retry="6"):
    a = start_attempt(db, user, paper, "practice", [n])
    save_answer(db, a, n, first)
    submit(db, a)
    r = a.responses[0]
    submit_retry(db, r, retry)
    return r


@pytest.fixture
def response(db, junior_paper, child):
    return _miss(db, junior_paper, child)  # Junior Q2 answer is 21


@pytest.fixture
def response_with_photo(db, settings, response):
    buf = io.BytesIO()
    Image.new("RGB", (50, 50), "white").save(buf, "PNG")
    store_photo(db, settings, response, buf.getvalue())
    return response


def solved(answer="21"):
    return ReferenceSolution(steps=["Add them.", "So the answer is 21."], final_answer=answer)


def diag(label="technique", **kw):
    base = dict(label=label, wrong_step=None, technique_tag="parity",
                hint="Think about odd and even.", explanation="You needed parity here.")
    base.update(kw)
    return Diagnosis(**base)


def crops(settings, response):
    return [settings.data_dir / p for p in response.paper_question.crop_paths]


def test_verified_solution_cached(db, settings, fake_ai, response):
    fake_ai.add(ReferenceSolution, solved())
    p = response.paper_question.problem
    assert ensure_reference_solution(db, p, crops(settings, response), fake_ai) is True
    assert ensure_reference_solution(db, p, crops(settings, response), fake_ai) is True
    assert fake_ai.calls(ReferenceSolution) == 1 and p.verified and "So the answer is 21." in p.reference_solution
    assert [c.effort for c in fake_ai.log if c.schema is ReferenceSolution] == ["high"]


def test_second_try_can_verify(db, settings, fake_ai, response):
    fake_ai.add(ReferenceSolution, solved("20"), solved("21"))
    assert ensure_reference_solution(db, response.paper_question.problem, crops(settings, response), fake_ai)


def test_two_wrong_tries_unverified(db, settings, fake_ai, response):
    fake_ai.add(ReferenceSolution, solved("20"), solved("22"))
    p = response.paper_question.problem
    assert ensure_reference_solution(db, p, crops(settings, response), fake_ai) is False
    assert p.verified is False and p.reference_solution is None


def test_ai_error_leaves_unverified_for_later(db, settings, fake_ai, response):
    fake_ai.add(ReferenceSolution, AIError("down"))
    p = response.paper_question.problem
    assert ensure_reference_solution(db, p, crops(settings, response), fake_ai) is False
    assert p.verified is None


def test_diagnosis_stored(db, settings, fake_ai, response_with_photo):
    fake_ai.add(ReferenceSolution, solved()).add(Diagnosis, diag("careless", wrong_step="7 × 8 = 54"))
    diagnose_response(db, response_with_photo.id, fake_ai, settings)
    db.refresh(response_with_photo)
    r = response_with_photo
    assert r.label == Label.careless and r.diagnosis_status == DiagnosisStatus.done
    assert r.diagnosis["wrong_step"] == "7 × 8 = 54"
    call = fake_ai.last_call
    assert call.images[-1].name.endswith(".jpg") and call.effort == "medium"
    assert "21" in call.text and "5" in call.text and "6" in call.text and "attached" in call.text


def test_no_photo_says_so(db, settings, fake_ai, response):
    fake_ai.add(ReferenceSolution, solved()).add(Diagnosis, diag("unsure"))
    diagnose_response(db, response.id, fake_ai, settings)
    assert "not provided" in fake_ai.last_call.text
    assert all(not p.name.endswith(".jpg") for p in fake_ai.last_call.images)


def test_unverified_gives_unsure_without_diagnosis_call(db, settings, fake_ai, response):
    fake_ai.add(ReferenceSolution, solved("1"), solved("2"))
    diagnose_response(db, response.id, fake_ai, settings)
    db.refresh(response)
    assert response.label == Label.unsure and response.diagnosis == {"unverified": True}
    assert fake_ai.calls(Diagnosis) == 0


def test_ai_error_gives_unsure(db, settings, fake_ai, response):
    fake_ai.add(ReferenceSolution, solved()).add(Diagnosis, AIError("timeout"))
    diagnose_response(db, response.id, fake_ai, settings)
    db.refresh(response)
    assert response.label == Label.unsure and response.diagnosis_status == DiagnosisStatus.failed


def test_refusal_gives_unsure(db, settings, fake_ai, response):
    fake_ai.add(ReferenceSolution, AIRefusal("no"))
    diagnose_response(db, response.id, fake_ai, settings)
    db.refresh(response)
    assert response.label == Label.unsure


# ---- web ----

def _done(db, r, label, diagnosis, verified=True):
    p = r.paper_question.problem
    p.verified = verified
    p.reference_solution = "1. Add them.\n2. So the answer is **21**." if verified else None
    r.label, r.diagnosis, r.diagnosis_status = label, diagnosis, DiagnosisStatus.done
    db.commit()


def test_unverified_never_shows_solution(child_client, db, parent, response):
    _done(db, response, Label.unsure, {"unverified": True}, verified=False)
    html = child_client.get(f"/responses/{response.id}/feedback").text
    assert "Go through it with Dad" in html and "Show full solution" not in html


def test_careless_card_quotes_step(child_client, db, parent, response):
    _done(db, response, Label.careless, diag("careless", wrong_step="7 × 8 = 54").model_dump())
    html = child_client.get(f"/responses/{response.id}/feedback").text
    assert "7 × 8 = 54" in html and "Careless slip" in html and "Show full solution" in html


def test_technique_card_hint_then_solution(child_client, db, parent, response):
    _done(db, response, Label.technique, diag().model_dump())
    html = child_client.get(f"/responses/{response.id}/feedback").text
    assert html.index("Think about odd and even.") < html.index("Show full solution")
    assert "Odd and even" in html  # technique name from seeded table / TECHNIQUES
    assert "<strong>21</strong>" in html  # markdown rendered


def test_ai_text_is_escaped(child_client, db, parent, response):
    _done(db, response, Label.technique, diag(explanation="<script>alert(1)</script>").model_dump())
    assert "<script>alert(1)</script>" not in child_client.get(f"/responses/{response.id}/feedback").text


def test_pending_card_polls(child_client, db, parent, response):
    response.diagnosis_status = DiagnosisStatus.pending
    db.commit()
    html = child_client.get(f"/responses/{response.id}/feedback").text
    assert "hx-trigger" in html


def test_feedback_404_before_submit(child_client, db, junior_paper, child):
    a = start_attempt(db, child, junior_paper, "practice", [1])
    assert child_client.get(f"/responses/{a.responses[0].id}/feedback").status_code == 404
    assert child_client.get(f"/attempts/{a.id}/feedback").status_code == 404


def test_attempt_feedback_lists_misses(child_client, db, parent, response):
    _done(db, response, Label.technique, diag().model_dump())
    html = child_client.get(f"/attempts/{response.attempt_id}/feedback").text
    assert "Question 2" in html


def test_parent_can_rediagnose(parent_client, db, fake_ai, response):
    fake_ai.add(ReferenceSolution, solved()).add(Diagnosis, diag())
    parent_client.post(f"/parent/responses/{response.id}/rediagnose")
    db.refresh(response)
    assert response.label == Label.technique


def test_child_cannot_rediagnose(child_client, response):
    assert child_client.post(f"/parent/responses/{response.id}/rediagnose").status_code == 403
