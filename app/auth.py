from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from sqlalchemy.orm import Session

from app.models import Role, User

_ph = PasswordHasher()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_user(db: Session, username: str, display_name: str, role: Role, password: str) -> User:
    u = User(username=username, display_name=display_name, role=role, password_hash=hash_password(password))
    db.add(u)
    db.commit()
    return u


# ---- web layer ----
from fastapi import APIRouter, Depends, Form, HTTPException, Request  # noqa: E402
from fastapi.responses import RedirectResponse  # noqa: E402

from app.db import get_db  # noqa: E402


class NotLoggedIn(Exception):
    pass


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    uid = request.session.get("uid")
    user = db.get(User, uid) if uid else None
    if user is None:
        raise NotLoggedIn()
    request.state.user = user
    return user


def require_user(user: User = Depends(current_user)) -> User:
    return user


def require_parent(user: User = Depends(current_user)) -> User:
    if user.role != Role.parent:
        raise HTTPException(status_code=403, detail="Parents only")
    return user


def home_for(user: User) -> str:
    return "/parent" if user.role == Role.parent else "/practice"


router = APIRouter()


@router.get("/login")
def login_page(request: Request):
    from app.web import render
    return render(request, "login.html")


@router.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    from app.web import render
    user = db.query(User).filter(User.username == username.strip()).one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        return render(request, "login.html", status_code=401, error="Wrong username or password.")
    request.session.clear()
    request.session["uid"] = user.id
    return RedirectResponse(home_for(user), status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/")
def root(user: User = Depends(current_user)):
    return RedirectResponse(home_for(user), status_code=303)
