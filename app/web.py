import re
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates
from markdown_it import MarkdownIt
from markupsafe import Markup, escape

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
_MD = MarkdownIt("commonmark", {"html": False})
_MATH = re.compile(r"(\$\$.+?\$\$|\$[^$\n]+?\$)", re.S)


def md(text: str | None) -> Markup:
    """Render untrusted Markdown (raw HTML disabled), keeping $...$ maths intact for KaTeX."""
    if not text:
        return Markup("")
    spans: list[str] = []

    def keep(m):
        spans.append(str(escape(m.group(0))))
        return f"@@MATH{len(spans) - 1}@@"

    html = _MD.render(_MATH.sub(keep, text))
    html = re.sub(r"@@MATH(\d+)@@", lambda m: spans[int(m.group(1))], html)
    return Markup(html)


TEMPLATES.env.filters["md"] = md


def render(request: Request, name: str, status_code: int = 200, **ctx):
    ctx.setdefault("user", getattr(request.state, "user", None))
    return TEMPLATES.TemplateResponse(request, name, ctx, status_code=status_code)
