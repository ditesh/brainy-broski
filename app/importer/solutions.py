"""Read official answers exactly from worked-solution pages that have a text layer
(for example SASMO books: "Question 16 ... Answer: 59")."""
import re
from pathlib import Path

import pymupdf as fitz

_HEADING = re.compile(r"(?m)^\s*Question\s+(\d{1,3})\s*$")
_ANSWER = re.compile(r"Answer\s*:\s*\(?\s*([A-E]|[-−]?\d[\d,]*(?:\.\d+)?(?:\s*/\s*\d+)?)\s*\)?")


def answers_from_solutions(pdf: Path, first_page: int, last_page: int) -> dict[int, str]:
    """{question number: answer} for every solution whose "Answer:" line could be read."""
    try:
        with fitz.open(pdf) as doc:
            pages = range(max(first_page, 1) - 1, min(last_page, doc.page_count))
            text = "\n".join(doc[i].get_text() for i in pages)
    except Exception:
        return {}
    chunks = _HEADING.split(text)
    out: dict[int, str] = {}
    for n, body in zip(chunks[1::2], chunks[2::2]):
        m = _ANSWER.search(body)
        if m and int(n) not in out:
            out[int(n)] = re.sub(r"\s+", "", m.group(1)).replace("−", "-").replace(",", "")
    return out
