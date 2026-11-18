import argparse
import getpass
import sqlite3
from datetime import date

from sqlalchemy.orm import sessionmaker

from app.auth import create_user
from app.config import get_settings
from app.db import Base, make_engine
from app.models import Role
from app.techniques import seed_techniques


def _session():
    s = get_settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    eng = make_engine(s.database_url)
    import app.models  # noqa: F401
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng, expire_on_commit=False)()


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db")
    sub.add_parser("seed-techniques")
    sub.add_parser("backup", help="copy the SQLite database to DATA_DIR/backups/app-YYYY-MM-DD.db")
    cu = sub.add_parser("create-user")
    cu.add_argument("username")
    cu.add_argument("--role", choices=[r.value for r in Role], required=True)
    cu.add_argument("--display-name", required=True)
    cu.add_argument("--password", help="omit to be prompted")
    a = p.parse_args(argv)
    if a.cmd == "backup":
        backup()
        return
    db = _session()
    if a.cmd == "init-db":
        print("database ready")
    elif a.cmd == "seed-techniques":
        seed_techniques(db)
        print("techniques seeded")
    elif a.cmd == "create-user":
        pw = a.password or getpass.getpass("Password: ")
        create_user(db, a.username, a.display_name, Role(a.role), pw)
        print(f"created {a.role} {a.username}")


def backup() -> None:
    s = get_settings()
    src_path = s.database_url.removeprefix("sqlite:///")
    out_dir = s.data_dir / "backups"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"app-{date.today().isoformat()}.db"
    src, dst = sqlite3.connect(src_path), sqlite3.connect(out)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    for old in sorted(out_dir.glob("app-*.db"))[:-14]:  # keep two weeks
        old.unlink()
    print(f"backup written to {out}")


if __name__ == "__main__":
    main()
