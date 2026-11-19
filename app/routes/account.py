"""Account page: change your name, your password, and (for kids) a fun profile."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app import auth
from app.auth import current_user, hash_password, verify_password
from app.db import get_db
from app.models import Role, User
from app.profile import AVATARS, TEXT_FIELDS, ProfileError, clean_profile
from app.web import render

router = APIRouter()
NAME_MAX = 40
PASSWORD_MIN, PASSWORD_MAX = 6, 128


def _page(request: Request, user: User, status_code: int = 200, **ctx):
    return render(request, "account.html", status_code=status_code, avatars=AVATARS, text_fields=TEXT_FIELDS,
                  profile=user.profile or {}, is_child=user.role == Role.child, **ctx)


@router.get("/account")
def account(request: Request, user: User = Depends(current_user)):
    return _page(request, user)


@router.post("/account/profile")
async def save_profile(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    form = dict(await request.form())
    name = (form.get("display_name") or "").strip()
    if not name or len(name) > NAME_MAX:
        return _page(request, user, 400, profile_error=f"Your name needs 1 to {NAME_MAX} letters.")
    profile = None
    if user.role == Role.child:
        try:
            profile = clean_profile(form)
        except ProfileError as e:
            return _page(request, user, 400, profile_error=str(e))
    user.display_name, user.profile = name, profile or None
    db.commit()
    return _page(request, user, profile_saved=True)


@router.post("/account/password")
async def change_password(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    form = await request.form()
    current, new, confirm = (form.get(k) or "" for k in ("current_password", "new_password", "confirm_password"))
    key = f"pw:{user.id}"
    if auth._locked_out(key):
        return _page(request, user, 429, pw_error="Too many wrong tries. Wait 15 minutes and try again.")
    if not verify_password(current, user.password_hash):
        auth._record_failure(key)
        return _page(request, user, 400, pw_error="That's not your current password.")
    if new != confirm:
        return _page(request, user, 400, pw_error="The two new passwords don't match.")
    if not PASSWORD_MIN <= len(new) <= PASSWORD_MAX:
        return _page(request, user, 400, pw_error=f"Use at least {PASSWORD_MIN} characters.")
    user.password_hash = hash_password(new)
    user.session_gen = (user.session_gen or 0) + 1  # other devices must log in again
    db.commit()
    request.session["gen"] = user.session_gen  # ...but not this one
    return _page(request, user, pw_saved=True)
