import threading
import time
from collections import defaultdict, deque

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from sqlalchemy.orm import Session

from app.models import Role, User

# OWASP-recommended low-memory argon2id profile (19 MiB), fine for a 512 MB VM
_ph = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
_hash_slots = threading.BoundedSemaphore(4)  # cap concurrent hashing
_DUMMY_HASH = _ph.hash("not-a-real-password")

FAIL_LIMIT, FAIL_WINDOW = 10, 15 * 60
_failures: dict[str, deque] = defaultdict(deque)
_fail_lock = threading.Lock()


def _locked_out(key: str) -> bool:
    now = time.monotonic()
    with _fail_lock:
        q = _failures[key]
        while q and now - q[0] > FAIL_WINDOW:
            q.popleft()
        return len(q) >= FAIL_LIMIT


def _record_failure(key: str) -> None:
    with _fail_lock:
        _failures[key].append(time.monotonic())


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    with _hash_slots:
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
    name = username.strip().lower()
    ip = request.client.host if request.client else "?"
    keys = (f"u:{name}", f"ip:{ip}")
    if any(_locked_out(k) for k in keys):
        return render(request, "login.html", status_code=429,
                      error="Too many wrong tries. Wait 15 minutes and try again.")
    user = db.query(User).filter(User.username == username.strip()).one_or_none()
    ok = verify_password(password, user.password_hash if user else _DUMMY_HASH) and user is not None
    if not ok:
        for k in keys:
            _record_failure(k)
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
