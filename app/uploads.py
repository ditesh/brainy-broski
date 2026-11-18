import io
import secrets
from datetime import timedelta
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Response, UploadToken, utcnow

MAX_SIDE = 2000


class UnsupportedImage(Exception):
    pass


def new_upload_token(db: Session, response: Response, minutes: int = 15) -> UploadToken:
    t = UploadToken(token=secrets.token_urlsafe(16), response_id=response.id,
                    expires_at=utcnow() + timedelta(minutes=minutes))
    db.add(t)
    db.commit()
    return t


def valid_token(db: Session, token: str) -> UploadToken | None:
    t = db.get(UploadToken, token)
    if t is None or t.used_at is not None or utcnow() >= t.expires_at:
        return None
    return t


def store_photo(db: Session, settings: Settings, response: Response, data: bytes) -> Path:
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise UnsupportedImage(str(e)) from e
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        bg = Image.new("RGB", img.size, "white")
        bg.paste(img, mask=img.convert("RGBA").split()[-1])
        img = bg
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    rel = Path("photos") / str(response.attempt.user_id) / f"{response.id}.jpg"
    out = settings.data_dir / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "JPEG", quality=85)
    response.photo_path = str(rel)
    db.commit()
    return out
