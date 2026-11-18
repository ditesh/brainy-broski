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
FIGURE_MARK = re.compile(r"^\s*\[\[figure\]\]\s*$", re.M | re.I)


def question_html(text: str | None, figure_paths: list | None) -> Markup:
    """Question text with its pictures placed at [[figure]] markers; spare pictures go at the end."""
    figs = [f'<img class="qfig" src="/files/{escape(p)}" alt="Diagram for this question">' for p in (figure_paths or [])]
    pieces = FIGURE_MARK.split(text or "")
    html = []
    for i, piece in enumerate(pieces):
        html.append(str(md(piece)))
        if i < len(pieces) - 1 and figs:
            html.append(figs.pop(0))
    html.extend(figs)
    return Markup("".join(html))


TEMPLATES.env.globals["question_html"] = question_html


def render(request: Request, name: str, status_code: int = 200, **ctx):
    from app.daily import fact_for, local_today, symbol_for
    ctx.setdefault("user", getattr(request.state, "user", None))
    today = local_today(request.app.state.settings.timezone)
    ctx.update(today_key=today.isoformat(), today_symbol=f"Today's symbol: {symbol_for(today).name}",
               today_fact=fact_for(today))
    return TEMPLATES.TemplateResponse(request, name, ctx, status_code=status_code)
