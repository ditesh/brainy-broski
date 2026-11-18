from datetime import date

from fastapi import (APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request,
                     UploadFile)
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.ai.client import AIClient, get_ai
from app.ai.schemas import PdfStructure
from app.auth import require_parent
from app.db import get_db
from app.fetch import FetchError, fetch_pdf
from app.importer.pipeline import detect_structure, run_import
from app.models import ImportStatus, Paper, SourcePdf, User
from app.web import render

router = APIRouter()
CONTESTS = ["IMONST1", "IMONST2", "SASMO", "Kangaroo", "ASMO", "Other"]


@router.get("/parent")
def parent_home(request: Request, user: User = Depends(require_parent), db: Session = Depends(get_db)):
    sources = db.query(SourcePdf).order_by(SourcePdf.uploaded_at.desc()).all()
    papers = {s.id: db.query(Paper).filter_by(source_pdf_id=s.id).all() for s in sources}
    return render(request, "parent_home.html", sources=sources, papers=papers)


@router.get("/parent/import")
def import_form(request: Request, user: User = Depends(require_parent)):
    return render(request, "import_upload.html", contests=CONTESTS, this_year=date.today().year)


def _english_categories(src: SourcePdf) -> list[str]:
    if not src.structure:
        return []
    st = PdfStructure.model_validate(src.structure)
    seen: list[str] = []
    for s in st.sections:
        if s.language == "en" and s.category not in seen:
            seen.append(s.category)
    return seen


def _status_page(request: Request, db: Session, src: SourcePdf, status_code: int = 200):
    papers = db.query(Paper).filter_by(source_pdf_id=src.id).all()
    return render(request, "import_status.html", status_code=status_code, src=src,
                  categories=_english_categories(src), papers=papers)


@router.post("/parent/import")
async def import_upload(request: Request, background: BackgroundTasks,
                        file: UploadFile | None = File(None), url: str = Form(""), contest: str = Form(...),
                        year: int = Form(...), duration_min: str = Form(""), user: User = Depends(require_parent),
                        db: Session = Depends(get_db), ai: AIClient = Depends(get_ai)):
    def fail(msg: str):
        return render(request, "import_upload.html", status_code=400, contests=CONTESTS,
                      this_year=date.today().year, error=msg, url=url)

    data = await file.read() if file is not None and file.filename else b""
    filename = file.filename if data else ""
    if not data and url.strip():
        try:
            filename, data = await run_in_threadpool(
                fetch_pdf, url, getattr(request.app.state, "http_transport", None),
                getattr(request.app.state, "resolve_host", None))
        except FetchError as e:
            return fail(str(e))
    if not data:
        return fail("Choose a PDF file or paste a link to one.")
    if not data.startswith(b"%PDF"):
        return fail("That file isn't a PDF. Please choose the paper's PDF file.")
    settings = request.app.state.settings
    src = SourcePdf(filename=filename or "paper.pdf", path="", contest=contest, year=year,
                    duration_min=int(duration_min) if duration_min.strip().isdigit() else None)
    db.add(src)
    db.flush()
    pdf_dir = settings.data_dir / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    path = pdf_dir / f"{src.id}.pdf"
    path.write_bytes(data)
    src.path = str(path)
    db.commit()
    background.add_task(_job, request.app, detect_structure, src.id)
    return RedirectResponse(f"/parent/import/{src.id}", status_code=303)


def _job(app, fn, *args):
    db = app.state.session_factory()
    try:
        fn(*args, db, app.state.ai, app.state.settings)
    finally:
        db.close()


def _get_src(db: Session, src_id: int) -> SourcePdf:
    src = db.get(SourcePdf, src_id)
    if src is None:
        raise HTTPException(404)
    db.refresh(src)
    return src


@router.get("/parent/import/{src_id}")
def import_status(src_id: int, request: Request, user: User = Depends(require_parent),
                  db: Session = Depends(get_db)):
    src = _get_src(db, src_id)
    if request.headers.get("HX-Request"):
        return render(request, "_import_status_body.html", src=src, categories=_english_categories(src),
                      papers=db.query(Paper).filter_by(source_pdf_id=src.id).all())
    return _status_page(request, db, src)


@router.post("/parent/import/{src_id}")
def import_choose(src_id: int, request: Request, background: BackgroundTasks,
                  categories: list[str] = Form(default=[]), user: User = Depends(require_parent),
                  db: Session = Depends(get_db), ai: AIClient = Depends(get_ai)):
    src = _get_src(db, src_id)
    allowed = [c for c in categories if c in _english_categories(src)]
    if not allowed:
        return _status_page(request, db, src, status_code=400)
    src.status = ImportStatus.running
    db.commit()
    background.add_task(_job, request.app, run_import, src.id, allowed)
    return _status_page(request, db, src)


@router.post("/parent/import/{src_id}/retry")
def import_retry(src_id: int, request: Request, background: BackgroundTasks,
                 user: User = Depends(require_parent), db: Session = Depends(get_db),
                 ai: AIClient = Depends(get_ai)):
    src = _get_src(db, src_id)
    if src.structure:
        src.status, src.error = ImportStatus.needs_review, None
        db.commit()
    else:
        background.add_task(_job, request.app, detect_structure, src.id)
    return RedirectResponse(f"/parent/import/{src.id}", status_code=303)
