import io
from datetime import timedelta

import pytest
from freezegun import freeze_time
from PIL import Image

from app.models import DiagnosisStatus, UploadToken, utcnow
from app.practice.service import save_answer, start_attempt, submit, submit_retry
from app.uploads import UnsupportedImage, new_upload_token, store_photo


@pytest.fixture
def miss_response(db, junior_paper, child, fake_ai):
    from app.ai.schemas import Diagnosis, ReferenceSolution
    fake_ai.respond(ReferenceSolution, lambda c: ReferenceSolution(steps=["x"], final_answer="18"))
    fake_ai.respond(Diagnosis, lambda c: Diagnosis(label="careless", hint="h", explanation="e"))
    a = start_attempt(db, child, junior_paper, "practice", [1, 2])
    save_answer(db, a, 1, "81")
    submit(db, a)
    r = next(x for x in a.responses if x.paper_question.number == 1)
    submit_retry(db, r, "80")
    return r


def _jpeg(size=(4000, 3000), orientation=6) -> bytes:
    img = Image.new("RGB", size, "white")
    exif = Image.Exif()
    exif[0x0112] = orientation
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif.tobytes())
    return buf.getvalue()


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (800, 600), (255, 255, 255, 0)).save(buf, "PNG")
    return buf.getvalue()


def test_exif_rotated_photo_stored_upright(db, settings, miss_response):
    p = store_photo(db, settings, miss_response, _jpeg())
    w, h = Image.open(p).size
    assert h > w and max(w, h) == 2000
    assert miss_response.photo_path == f"photos/{miss_response.attempt.user_id}/{miss_response.id}.jpg"


def test_png_accepted(db, settings, miss_response):
    p = store_photo(db, settings, miss_response, _png())
    assert Image.open(p).format == "JPEG"


def test_unsupported_file_raises(db, settings, miss_response):
    with pytest.raises(UnsupportedImage):
        store_photo(db, settings, miss_response, b"%PDF-1.4 not an image")


def test_phone_upload_flow(client, db, miss_response):
    t = new_upload_token(db, miss_response)
    page = client.get(f"/u/{t.token}")
    assert page.status_code == 200 and "Take photo" in page.text
    r = client.post(f"/u/{t.token}", files={"photo": ("w.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 200 and "Got it" in r.text
    db.refresh(miss_response)
    assert miss_response.photo_path and miss_response.diagnosis_status != DiagnosisStatus.none


def test_unsupported_file_friendly_error(client, db, miss_response):
    t = new_upload_token(db, miss_response)
    r = client.post(f"/u/{t.token}", files={"photo": ("x.pdf", b"%PDF-1.4", "application/pdf")})
    assert r.status_code == 400 and "photo" in r.text.lower()
    db.refresh(t)
    assert t.used_at is None  # can try again with a real photo


def test_token_single_use(client, db, miss_response):
    t = new_upload_token(db, miss_response)
    assert client.post(f"/u/{t.token}", files={"photo": ("w.png", _png(), "image/png")}).status_code == 200
    r = client.post(f"/u/{t.token}", files={"photo": ("w.png", _png(), "image/png")})
    assert r.status_code == 410 and "expired" in r.text


def test_token_expires(client, db, miss_response):
    t = new_upload_token(db, miss_response)
    with freeze_time(utcnow() + timedelta(minutes=16)):
        assert client.get(f"/u/{t.token}").status_code == 410


def test_unknown_token(client):
    assert client.get("/u/nope").status_code == 410


def test_token_page_reveals_nothing(client, db, miss_response):
    miss_response.paper_question.problem.answer = "987654321"
    db.commit()
    t = new_upload_token(db, miss_response)
    html = client.get(f"/u/{t.token}").text
    assert "987654321" not in html and "crops/" not in html


def test_photo_page_shows_qr_and_laptop_input(child_client, miss_response):
    html = child_client.get(f"/responses/{miss_response.id}/photo").text
    assert "<svg" in html and 'capture="environment"' in html and "/u/" in html


def test_laptop_upload(child_client, db, miss_response):
    r = child_client.post(f"/responses/{miss_response.id}/photo",
                          files={"photo": ("w.png", _png(), "image/png")}, follow_redirects=False)
    assert r.status_code == 303
    db.refresh(miss_response)
    assert miss_response.photo_path


def test_skip_photo_enqueues_diagnosis(child_client, db, miss_response):
    child_client.post(f"/responses/{miss_response.id}/skip-photo")
    db.refresh(miss_response)
    assert miss_response.diagnosis_status != DiagnosisStatus.none and miss_response.photo_path is None


def test_other_child_cannot_open_photo_page(child2_client, miss_response):
    assert child2_client.get(f"/responses/{miss_response.id}/photo").status_code == 404


def test_photo_only_for_misses_after_retry(child_client, db, junior_paper, child):
    a = start_attempt(db, child, junior_paper, "practice", [1])
    save_answer(db, a, 1, "18")
    submit(db, a)
    assert child_client.get(f"/responses/{a.responses[0].id}/photo").status_code == 400
