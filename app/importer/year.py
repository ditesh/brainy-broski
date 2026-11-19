"""Guess which year a past paper is from, before Claude has read it."""
import re
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

UNKNOWN_YEAR = 0  # stored when no year is known yet; Claude's structure pass may fill it in
_YEAR = re.compile(r"(?<!\d)(19\d\d|20\d\d)(?!\d)")


def _years(text: str) -> list[int]:
    hi = date.today().year + 1
    return [y for y in map(int, _YEAR.findall(text or "")) if 1990 <= y <= hi]


def _pdf_text(path: Path, pages: int = 2) -> str:
    try:
        import pymupdf as fitz
        with fitz.open(path) as doc:
            return "\n".join(doc[i].get_text() for i in range(min(pages, doc.page_count)))
    except Exception:
        return ""


def guess_year(filename: str, url: str, pdf_path: Path) -> int | None:
    """File name first (people name papers by year), then the most common year on the first pages,
    then the link (often only the upload date, so it's the weakest signal)."""
    if ys := _years(Path(filename or "").stem):
        return ys[0]
    if ys := _years(_pdf_text(pdf_path)):
        counts = Counter(ys)
        return max(ys, key=lambda y: (counts[y], -ys.index(y)))
    if ys := _years(urlparse(url or "").path):
        return ys[0]
    return None
