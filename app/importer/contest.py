"""Guess which contest a past paper is from, before Claude has read it."""
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from app.importer.year import _pdf_text

CONTESTS = ["IMONST1", "IMONST2", "SASMO", "Kangaroo", "ASMO", "Other"]
UNKNOWN_CONTEST = ""  # stored until the contest is known; the structure pass settles it

# Letters/digits on either side would make it part of another word (SASMO contains "asmo";
# "imonst-2020" is round 1 of 2020, not round 2).
_PATTERNS = [
    ("IMONST2", r"(?<![a-z])imonst[\s_-]*2(?!\d)|second round"),
    ("IMONST1", r"(?<![a-z])imonst(?:[\s_-]*1(?!\d))?|national selection test|imo-malaysia"),
    ("SASMO", r"(?<![a-z])sasmo(?![a-z])|singapore and asian schools math"),
    ("Kangaroo", r"kangaroo|k[äa]nguru"),
    ("ASMO", r"(?<![a-z])asmo(?![a-z])|asian science and mathematics olympiad"),
]


def _hits(text: str) -> Counter:
    text = (text or "").lower()
    hits = Counter({name: len(re.findall(p, text)) for name, p in _PATTERNS})
    if hits["IMONST2"]:  # an "IMONST 2" also matches the bare "imonst" pattern
        hits["IMONST1"] = max(0, hits["IMONST1"] - hits["IMONST2"])
    return +hits


def _best(text: str) -> str | None:
    hits = _hits(text)
    return hits.most_common(1)[0][0] if hits else None


def guess_contest(filename: str, url: str, pdf_path: Path) -> str | None:
    """File name first, then the link (its path and site), then the most mentioned contest on the first pages."""
    link = urlparse(url or "")
    return (_best(Path(filename or "").stem) or _best(f"{link.netloc} {link.path}")
            or _best(_pdf_text(pdf_path)))
