import sqlite3

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_missing_secret_key_fails_fast(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_backup_command_copies_database(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    con = sqlite3.connect(db_path)
    con.execute("create table t (x int)")
    con.execute("insert into t values (42)")
    con.commit()
    con.close()
    monkeypatch.setenv("SECRET_KEY", "x")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.config import get_settings
    get_settings.cache_clear()
    from app.cli import main
    main(["backup"])
    get_settings.cache_clear()
    backups = list((tmp_path / "backups").glob("app-*.db"))
    assert len(backups) == 1
    assert sqlite3.connect(backups[0]).execute("select x from t").fetchone() == (42,)
