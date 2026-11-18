from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from app import db as dbmod
from app.config import Settings, get_settings


def create_app(settings: Settings | None = None, session_factory: sessionmaker | None = None) -> FastAPI:
    settings = settings or get_settings()
    if session_factory is None:
        engine = dbmod.make_engine(settings.database_url)
        session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    dbmod.configure(session_factory)
    app = FastAPI(title="Olympiad Practice")
    app.state.settings = settings
    app.state.session_factory = session_factory

    @app.get("/health")
    def health():
        return {"ok": True}

    return app
