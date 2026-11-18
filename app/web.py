from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def render(request: Request, name: str, status_code: int = 200, **ctx):
    ctx.setdefault("user", getattr(request.state, "user", None))
    return TEMPLATES.TemplateResponse(request, name, ctx, status_code=status_code)
