from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
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

    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax",
                       https_only=False, max_age=60 * 60 * 24 * 30)
    app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

    from app.auth import NotLoggedIn, router as auth_router
    from app.routes import files, parent_import, parent_review, practice, upload

    @app.exception_handler(NotLoggedIn)
    def _not_logged_in(request: Request, exc: NotLoggedIn):
        return RedirectResponse("/login", status_code=303)

    app.include_router(auth_router)
    app.include_router(parent_import.router)
    app.include_router(practice.router)
    app.include_router(parent_review.router)
    app.include_router(files.router)
    app.include_router(upload.router)

    @app.get("/health")
    def health():
        return {"ok": True}

    return app
