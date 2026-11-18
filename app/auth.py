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
