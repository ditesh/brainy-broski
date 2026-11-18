"""Friendly error pages instead of raw JSON."""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.web import render

log = logging.getLogger(__name__)
HOME = [{"label": "Take me home", "href": "/"}]

COPY = {
    400: ("That didn't work", "Something in the form wasn't quite right. Go back and try again.", "🤔"),
    403: ("This page is for grown-ups", "Ask your parent if you need something here.", "🔒"),
    404: ("We couldn't find that page", "The link may be old, or the page has moved.", "🧭"),
    405: ("We couldn't find that page", "The link may be old, or the page has moved.", "🧭"),
    500: ("Something went wrong", "It's not your fault! Try again, and if it keeps happening, tell your parent.", "🛠️"),
}
_DEFAULT_DETAILS = {"Bad Request", "Forbidden", "Not Found", "Method Not Allowed", "Internal Server Error"}


def _page(request: Request, status: int, detail: str | None = None):
    title, message, icon = COPY.get(status, COPY[500] if status >= 500 else COPY[400])
    if status == 403 and getattr(request.state, "user", None) is not None and request.state.user.role.value == "parent":
        title, message = "You can't open this page", "This page belongs to someone else."
    if detail and detail not in _DEFAULT_DETAILS and status not in (403, 404):
        message = detail
    template = "_error_fragment.html" if request.headers.get("HX-Request") else "error.html"
    return render(request, template, status_code=status, title=title, message=message, icon=icon, actions=HOME)


def install(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        return _page(request, exc.status_code, exc.detail if isinstance(exc.detail, str) else None)

    @app.exception_handler(RequestValidationError)
    async def form_error(request: Request, exc: RequestValidationError):
        return _page(request, 400)

    @app.exception_handler(Exception)
    async def crash(request: Request, exc: Exception):
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return _page(request, 500)
