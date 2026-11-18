import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import Base, make_engine, get_db


@pytest.fixture(autouse=True)
def _reset_login_lockouts():
    from app import auth
    auth._failures.clear()
    yield
    auth._failures.clear()


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
    from tests.support.fake_ai import FakeAI
    return FakeAI()


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
    from app.ai.client import get_ai
    application.dependency_overrides[get_ai] = lambda: fake_ai
    application.state.ai = fake_ai
    return application


@pytest.fixture
def client(app):
    return TestClient(app)


from app.auth import create_user  # noqa: E402
from app.models import Role  # noqa: E402


@pytest.fixture
def parent(db):
    return create_user(db, "dad", "Dad", Role.parent, "pw")


@pytest.fixture
def child(db):
    return create_user(db, "kid", "Kid", Role.child, "pw")


@pytest.fixture
def child2(db):
    return create_user(db, "kid2", "Kid Two", Role.child, "pw")


def login_as(client, username, password="pw"):
    return client.post("/login", data={"username": username, "password": password}, follow_redirects=False)


@pytest.fixture
def parent_client(app, parent):
    c = TestClient(app)
    login_as(c, "dad")
    return c


@pytest.fixture
def child_client(app, child):
    c = TestClient(app)
    login_as(c, "kid")
    return c


@pytest.fixture
def child2_client(app, child2):
    c = TestClient(app)
    login_as(c, "kid2")
    return c


# ---- imported contest fixtures (Tasks 7+) ----
from app.ai.schemas import QuestionAnalysis  # noqa: E402
from app.importer.pipeline import run_import  # noqa: E402
from app.models import ImportStatus, Paper, PaperQuestion, SourcePdf  # noqa: E402
from tests.fixtures.make_pdf import build_contest_pdf, contest_layout, contest_structure_dict  # noqa: E402
from tests.support.contest import analysis_responder  # noqa: E402


@pytest.fixture
def contest_src(db, settings):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "pdfs").mkdir(exist_ok=True)
    path = build_contest_pdf(settings.data_dir / "pdfs" / "1.pdf", contest_layout())
    s = SourcePdf(filename="imonst.pdf", path=str(path), contest="IMONST", year=2020, duration_min=180,
                  structure=contest_structure_dict(), status=ImportStatus.needs_review)
    db.add(s)
    db.commit()
    return s


def _import(db, settings, fake_ai, src, categories, publish):
    fake_ai.respond(QuestionAnalysis, analysis_responder)
    run_import(src.id, categories, db, fake_ai, settings)
    papers = db.query(Paper).order_by(Paper.id).all()
    if publish:
        for p in papers:
            p.published = True
        db.commit()
    return papers


@pytest.fixture
def imported_paper(db, settings, fake_ai, contest_src):
    return _import(db, settings, fake_ai, contest_src, ["Junior"], publish=False)[0]


@pytest.fixture
def papers(db, settings, fake_ai, contest_src):
    """Primary + Junior, published."""
    ps = _import(db, settings, fake_ai, contest_src, ["Primary", "Junior"], publish=True)
    return {p.category: p for p in ps}


@pytest.fixture
def junior_paper(papers):
    return papers["Junior"]


def get_pq(db, paper, n):
    return db.query(PaperQuestion).filter_by(paper_id=paper.id, number=n).one()
