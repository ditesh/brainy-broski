import qrcode
from qrcode.image.svg import SvgPathImage
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.ai.client import AIClient, get_ai
from app.auth import require_user
from app.db import get_db
from app.diagnosis.service import enqueue_diagnosis
from app.models import Response, User, utcnow
from app.routes.practice import get_response
from app.uploads import UnsupportedImage, new_upload_token, store_photo, valid_token
from app.web import render

router = APIRouter()
MAX_BYTES = 25 * 1024 * 1024


def _photo_allowed(r: Response) -> None:
    if not (r.correct_first is False and r.correct_retry is False) or r.helped_out:
        raise HTTPException(400, "A photo is only needed for questions still wrong after the second try.")


def _qr_svg(url: str) -> str:
    return qrcode.make(url, image_factory=SvgPathImage, box_size=8).to_string(encoding="unicode")


@router.get("/responses/{response_id}/photo")
def photo_page(response_id: int, request: Request, user: User = Depends(require_user),
               db: Session = Depends(get_db), ai: AIClient = Depends(get_ai)):
    r = get_response(db, response_id, user)
    _photo_allowed(r)
    if request.headers.get("HX-Request"):
        return render(request, "_photo_status.html", r=r)
    settings = request.app.state.settings
    t = new_upload_token(db, r, settings.upload_token_minutes)
    base = (settings.base_url or str(request.base_url)).rstrip("/")
    url = f"{base}/u/{t.token}"
    return render(request, "photo.html", r=r, qr=_qr_svg(url), url=url, minutes=settings.upload_token_minutes)


async def _read(photo: UploadFile) -> bytes:
    data = await photo.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise UnsupportedImage("too large")
    return data


@router.post("/responses/{response_id}/photo")
async def photo_upload(response_id: int, request: Request, background: BackgroundTasks,
                       photo: UploadFile = File(...), user: User = Depends(require_user),
                       db: Session = Depends(get_db), ai: AIClient = Depends(get_ai)):
    r = get_response(db, response_id, user)
    _photo_allowed(r)
    try:
        store_photo(db, request.app.state.settings, r, await _read(photo))
    except UnsupportedImage:
        return render(request, "_photo_status.html", status_code=400, r=r,
                      error="That doesn't look like a photo. Please take a picture of your working.")
    enqueue_diagnosis(background, request.app, db, r)
    return RedirectResponse(f"/responses/{r.id}/feedback", status_code=303)


@router.post("/responses/{response_id}/skip-photo")
def skip_photo(response_id: int, request: Request, background: BackgroundTasks,
               user: User = Depends(require_user), db: Session = Depends(get_db), ai: AIClient = Depends(get_ai)):
    r = get_response(db, response_id, user)
    _photo_allowed(r)
    enqueue_diagnosis(background, request.app, db, r)
    return RedirectResponse(f"/responses/{r.id}/feedback", status_code=303)


def _expired(request: Request):
    return render(request, "phone_upload.html", status_code=410,
                  expired="This link has expired — make a new one on the laptop.")


@router.get("/u/{token}")
def phone_page(token: str, request: Request, db: Session = Depends(get_db)):
    t = valid_token(db, token)
    if t is None:
        return _expired(request)
    return render(request, "phone_upload.html", token=token, user=None)


@router.post("/u/{token}")
async def phone_upload(token: str, request: Request, background: BackgroundTasks,
                       photo: UploadFile = File(...), db: Session = Depends(get_db),
                       ai: AIClient = Depends(get_ai)):
    t = valid_token(db, token)
    if t is None:
        return _expired(request)
    r = db.get(Response, t.response_id)
    try:
        store_photo(db, request.app.state.settings, r, await _read(photo))
    except UnsupportedImage:
        return render(request, "phone_upload.html", status_code=400, token=token, user=None,
                      error="That doesn't look like a photo. Tap the button and take a picture of your working.")
    t.used_at = utcnow()
    db.commit()
    enqueue_diagnosis(background, request.app, db, r)
    return render(request, "phone_upload.html", done=True, user=None)
