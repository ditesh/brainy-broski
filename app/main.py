from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import sessionmaker

from app import db as dbmod
from app.config import Settings, get_settings


def create_app(settings: Settings | None = None, session_factory: sessionmaker | None = None) -> FastAPI:
    settings = settings or get_settings()
    if session_factory is None:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        engine = dbmod.make_engine(settings.database_url)
        dbmod.ensure_schema(engine)
        session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    dbmod.configure(session_factory)
    _reset_interrupted_jobs(session_factory)
    from app.importer.pipeline import backfill_figures
    try:
        backfill_figures(session_factory, settings)
        from app.diagnosis.service import fix_double_numbering
        with session_factory() as db:
            fix_double_numbering(db)
    except Exception:  # never block startup on this
        import logging
        logging.getLogger(__name__).exception("startup backfill failed")
    app = FastAPI(title="Brainy Broski")
    app.state.settings = settings
    app.state.session_factory = session_factory

    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax",
                       https_only=settings.secure_cookies, max_age=60 * 60 * 24 * 30)
    app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

    from app.auth import NotLoggedIn, router as auth_router
    from app.routes import account, feedback, goals, pets, files, parent_import, parent_review, practice, progress, upload

    @app.exception_handler(NotLoggedIn)
    def _not_logged_in(request: Request, exc: NotLoggedIn):
        return RedirectResponse("/login", status_code=303)

    from app import errors
    errors.install(app)

    app.include_router(auth_router)
    app.include_router(parent_import.router)
    app.include_router(practice.router)
    app.include_router(parent_review.router)
    app.include_router(files.router)
    app.include_router(upload.router)
    app.include_router(feedback.router)
    app.include_router(progress.router)
    app.include_router(account.router)
    app.include_router(goals.router)
    app.include_router(pets.router)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return RedirectResponse("/icon.svg", status_code=308)

    @app.get("/icon.svg", include_in_schema=False)
    def daily_icon():
        from app.daily import favicon_svg, local_today, symbol_for
        svg = favicon_svg(symbol_for(local_today(settings.timezone)))
        return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=3600"})

    @app.get("/health")
    def health():
        return {"ok": True}

    return app


def _reset_interrupted_jobs(session_factory: sessionmaker) -> None:
    """Background jobs die with the process; mark any left 'running'/'pending' as failed so they can be retried."""
    from sqlalchemy.exc import OperationalError

    from app.models import DiagnosisStatus, ImportStatus, Label, Response, SourcePdf
    db = session_factory()
    try:
        for src in db.query(SourcePdf).filter(SourcePdf.status == ImportStatus.running).all():
            src.status, src.error = ImportStatus.failed, "The import was interrupted. Press Retry."
        for r in db.query(Response).filter(Response.diagnosis_status == DiagnosisStatus.pending).all():
            r.diagnosis_status, r.label = DiagnosisStatus.failed, Label.unsure
        db.commit()
    except OperationalError:  # tables not created yet
        db.rollback()
    finally:
        db.close()
