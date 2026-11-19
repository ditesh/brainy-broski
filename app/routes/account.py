"""Account page: change your name, your password, and (for kids) a fun profile."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, object_session

from app import auth
from app.auth import current_user, hash_password, require_parent, verify_password
from app.db import get_db
from app.models import Role, User
from app.profile import AVATARS, TEXT_FIELDS, ProfileError, clean_profile
from app.web import render

router = APIRouter()
NAME_MAX = 40
PASSWORD_MIN, PASSWORD_MAX = 6, 128


def _page(request: Request, user: User, status_code: int = 200, **ctx):
    children = []
    if user.role == Role.parent:
        children = object_session(user).query(User).filter(User.role == Role.child).order_by(User.display_name).all()
    from app.routes.practice import child_goal
    return render(request, "account.html", status_code=status_code, avatars=AVATARS, text_fields=TEXT_FIELDS,
                  profile=user.profile or {}, is_child=user.role == Role.child, children=children,
                  goal=child_goal(request, object_session(user), user), **ctx)


def _new_password_problem(new: str, confirm: str) -> str | None:
    if new != confirm:
        return "The two new passwords don't match."
    if not PASSWORD_MIN <= len(new) <= PASSWORD_MAX:
        return f"Use at least {PASSWORD_MIN} characters."
    return None


def _set_password(user: User, new: str) -> None:
    user.password_hash = hash_password(new)
    user.session_gen = (user.session_gen or 0) + 1  # every device logged in as them must log in again


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
    if problem := _new_password_problem(new, confirm):
        return _page(request, user, 400, pw_error=problem)
    _set_password(user, new)
    db.commit()
    request.session["gen"] = user.session_gen  # ...except this one
    return _page(request, user, pw_saved=True)


@router.post("/account/children/{child_id}/password")
async def reset_child_password(child_id: int, request: Request, user: User = Depends(require_parent),
                               db: Session = Depends(get_db)):
    child = db.get(User, child_id)
    if child is None or child.role != Role.child:
        raise HTTPException(status_code=404)
    form = await request.form()
    new, confirm = (form.get(k) or "" for k in ("new_password", "confirm_password"))
    if problem := _new_password_problem(new, confirm):
        return _page(request, user, 400, reset_child=child.id, reset_error=problem)
    _set_password(child, new)
    db.commit()
    return _page(request, user, reset_child=child.id, reset_done=f"New password set for {child.display_name}.")
