from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(url: str, **kwargs) -> Engine:
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    eng = create_engine(url, connect_args=connect_args, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _fk(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()
    return eng


SessionLocal: sessionmaker | None = None


def configure(session_factory: sessionmaker) -> None:
    global SessionLocal
    SessionLocal = session_factory


def get_db() -> Iterator[Session]:
    assert SessionLocal is not None, "database not configured"
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
