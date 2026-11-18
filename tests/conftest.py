import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import Base, make_engine, get_db


@pytest.fixture
def settings(tmp_path):
    return Settings(database_url="sqlite://", data_dir=tmp_path / "data", secret_key="test-secret",
                    anthropic_api_key=None)


@pytest.fixture
def engine(settings):
    eng = make_engine(settings.database_url, poolclass=StaticPool)
    import app.models  # noqa: F401  register tables
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def db(session_factory):
    s = session_factory()
    yield s
    s.close()


@pytest.fixture
def fake_ai():
    return None  # filled in by Task 5


@pytest.fixture
def app(settings, session_factory, fake_ai):
    from app.main import create_app
    application = create_app(settings, session_factory=session_factory)

    def _db():
        s = session_factory()
        try:
            yield s
        finally:
            s.close()
    application.dependency_overrides[get_db] = _db
    return application


@pytest.fixture
def client(app):
    return TestClient(app)
