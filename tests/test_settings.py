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


def test_errors_never_echo_secret_values(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-very-secret-value")
    with pytest.raises(ValidationError) as e:
        Settings(_env_file=None)
    assert "very-secret" not in str(e.value)


def test_cli_explains_missing_secret_key(monkeypatch, capsys):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.chdir("/")  # no .env file here
    from app.config import get_settings
    get_settings.cache_clear()
    from app.cli import main
    with pytest.raises(SystemExit) as e:
        main(["init-db"])
    get_settings.cache_clear()
    assert e.value.code == 1
    assert "SECRET_KEY is not set" in capsys.readouterr().err
