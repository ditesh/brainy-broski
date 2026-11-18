from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(url: str, **kwargs) -> Engine:
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    if url.startswith("sqlite"):
        connect_args["timeout"] = 15
    eng = create_engine(url, connect_args=connect_args, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _pragmas(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=15000")
            if url not in ("sqlite://", "sqlite:///:memory:"):
                cur.execute("PRAGMA journal_mode=WAL")
            cur.close()
    return eng


def ensure_schema(engine: Engine) -> None:
    """Create missing tables and add any new nullable columns to existing SQLite tables."""
    import app.models  # noqa: F401  register tables
    from sqlalchemy import inspect, text
    Base.metadata.create_all(engine)
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in have and col.nullable:
                    ddl = col.type.compile(dialect=engine.dialect)
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl}'))


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
