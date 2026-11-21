import re
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates
from markdown_it import MarkdownIt
from markupsafe import Markup, escape

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
_MD = MarkdownIt("commonmark", {"html": False})
_MATH = re.compile(r"(\$\$.+?\$\$|\$[^$\n]+?\$)", re.S)


def md(text: str | None, inline: bool = False) -> Markup:
    """Render untrusted Markdown (raw HTML disabled), keeping $...$ maths intact for KaTeX."""
    if not text:
        return Markup("")
    spans: list[str] = []

    def keep(m):
        spans.append(str(escape(m.group(0))))
        return f"@@MATH{len(spans) - 1}@@"

    kept = _MATH.sub(keep, text)
    html = _MD.renderInline(kept) if inline else _MD.render(kept)
    html = re.sub(r"@@MATH(\d+)@@", lambda m: spans[int(m.group(1))], html)
    return Markup(html)


_OPTION = re.compile(r"^\s*\(([A-E])\)\s")
_NEXT_OPTION = re.compile(r"\s+(?=\([B-E]\)\s)")


def _option_item(o: str, choose: dict | None) -> str:
    """One option: plain text to read, or (when he's answering) a button that picks it."""
    if not choose:
        return f"<li>{md(o.strip(), inline=True)}</li>"
    letter = _OPTION.match(o).group(1)
    body = md(_OPTION.sub("", o, count=1).strip(), inline=True)
    sel = choose.get("selected") == letter
    return (f'<li><button type="submit" form="{escape(choose["form"])}" name="answer" value="{letter}" '
            f'class="mcq-choice{" selected" if sel else ""}" aria-pressed="{"true" if sel else "false"}">'
            f'<span class="mcq-letter">{letter}</span><span class="mcq-text">{body}</span></button></li>')


def has_mcq_options(text: str | None) -> bool:
    return "mcq-options" in _with_option_lists(text or "")


def _with_option_lists(text: str, choose: dict | None = None) -> str:
    """Multiple-choice options ("(A) ...", "(B) ...") become one list, one option per line. Markdown would
    otherwise run single lines together, and some papers print all the options on one line."""
    lines: list[str] = []
    for line in text.split("\n"):
        if _OPTION.match(line) and line.lstrip().startswith("(A)"):
            lines += _NEXT_OPTION.split(line.strip())
        else:
            lines.append(line)
    out, run = [], []

    def flush():
        if len(run) >= 2:
            items = "".join(_option_item(o, choose) for o in run)
            out.append(f'\n\n@@OPTS{len(_blocks)}@@\n\n')
            _blocks.append(f'<ul class="mcq-options{" answerable" if choose else ""}">{items}</ul>')
        elif run:
            out.extend(run + [""])
        run.clear()

    _blocks: list[str] = []
    for line in lines:
        if _OPTION.match(line):
            run.append(line)
        elif not line.strip() and run:
            continue  # blank lines between options
        else:
            flush()
            out.append(line)
    flush()
    html = str(md("\n".join(out)))
    for i, block in enumerate(_blocks):
        html = html.replace(f"<p>@@OPTS{i}@@</p>", block)
    return html


TEMPLATES.env.filters["md"] = md
FIGURE_MARK = re.compile(r"^\s*\[\[figure\]\]\s*$", re.M | re.I)


def question_html(text: str | None, figure_paths: list | None, choose: dict | None = None) -> Markup:
    """Question text with its pictures placed at [[figure]] markers; spare pictures go at the end.
    choose={"form": id, "selected": letter} turns multiple-choice options into buttons that answer."""
    figs = [f'<img class="qfig" src="/files/{escape(p)}" alt="Diagram for this question">' for p in (figure_paths or [])]
    pieces = FIGURE_MARK.split(text or "")
    html = []
    for i, piece in enumerate(pieces):
        html.append(_with_option_lists(piece, choose))
        if i < len(pieces) - 1 and figs:
            html.append(figs.pop(0))
    html.extend(figs)
    return Markup("".join(html))


TEMPLATES.env.globals["question_html"] = question_html
TEMPLATES.env.globals["has_mcq_options"] = has_mcq_options

from app.pets.art import pet_svg  # noqa: E402
from app.pets.creatures import CREATURES, STAGE_LABEL  # noqa: E402
TEMPLATES.env.globals.update(pet_svg=pet_svg, CREATURES=CREATURES, STAGE_LABEL=STAGE_LABEL)


def render(request: Request, name: str, status_code: int = 200, **ctx):
    from app.daily import fact_for, local_today, symbol_for
    ctx.setdefault("user", getattr(request.state, "user", None))
    today = local_today(request.app.state.settings.timezone)
    ctx.update(today_key=today.isoformat(), today_symbol=f"Today's symbol: {symbol_for(today).name}",
               today_fact=fact_for(today))
    return TEMPLATES.TemplateResponse(request, name, ctx, status_code=status_code)
