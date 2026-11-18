"""Build synthetic contest PDFs with PyMuPDF so tests never need copyrighted papers.

A layout is a list of pages; each page is a list of items:
  ("heading", text)            e.g. "Part A (1 point each)"
  ("problem", n, text)         rendered as "Problem n. text" (text may contain \n)
  ("text", text)               free text (e.g. continuation of a problem)
  ("gap", points)              vertical space
Every page gets a centred page-number footer.
"""
from pathlib import Path

import pymupdf as fitz

W, H = 595, 842
LEFT, TOP, LINE = 72, 72, 16


def build_contest_pdf(path: Path, layout: list[list[tuple]], label: str = "Problem") -> Path:
    doc = fitz.open()
    for pno, items in enumerate(layout, start=1):
        page = doc.new_page(width=W, height=H)
        y = TOP
        for item in items:
            kind = item[0]
            if kind == "gap":
                y += item[1]
                continue
            if kind == "heading":
                lines = [item[1]]
                font = "hebo"
            elif kind == "problem":
                lines = f"{label} {item[1]}. {item[2]}".split("\n")
                font = "helv"
            else:
                lines = item[1].split("\n")
                font = "helv"
            for ln in lines:
                page.insert_text((LEFT, y), ln, fontname=font, fontsize=11)
                y += LINE
            y += LINE // 2
        page.insert_text((W / 2 - 4, H - 40), str(pno), fontname="helv", fontsize=10)
    doc.save(str(path))
    doc.close()
    return path


def build_image_only_pdf(path: Path) -> Path:
    src = fitz.open()
    p = src.new_page(width=W, height=H)
    p.insert_text((LEFT, TOP), "Problem 1. scanned", fontsize=11)
    pix = p.get_pixmap(dpi=72)
    doc = fitz.open()
    page = doc.new_page(width=W, height=H)
    page.insert_image(page.rect, pixmap=pix)
    doc.save(str(path))
    return path


SAMPLE_LAYOUT = [
    [("heading", "Part A (1 point each)"),
     ("problem", 1, "What is 20 plus 20?"),
     ("problem", 2, "A broken watch lags 10 minutes\nevery 7 hours. How many hours in a week?"),
     ("problem", 3, "Find angle APC in degrees.")],
    [("problem", 4, "How many possible sums with 4 dice?"),
     ("problem", 5, "What is the age of the third child?"),
     ("heading", "Part B (2 points each)"),
     ("problem", 6, "What is the first digit of N?")],
    [("heading", "Answers"),
     ("problem", 1, "21"), ("problem", 2, "4"), ("problem", 3, "45")],
]

SPANNING_LAYOUT = [
    [("problem", 1, "Short question."),
     ("gap", 560),
     ("problem", 2, "This question starts near the bottom\nand keeps going")],
    [("text", "onto the next page with more words.\nWhat is the answer?"),
     ("problem", 3, "Final question.")],
]


# ---- multi-section contest used by import tests ----
PARTS = [("A", 1), ("B", 2), ("C", 3), ("D", 4)]


def question_text(category: str, n: int) -> str:
    # Junior Q1-5 repeat Primary Q6-10 word for word (like real IMONST papers)
    if category == "Junior" and n <= 5:
        return question_text("Primary", n + 5)
    return f"{category} question number {n} about topic {n * 7 % 11} with extra words"


def answer_for(category: str, n: int) -> str:
    if category == "Junior" and n <= 5:
        return answer_for("Primary", n + 5)
    return str(n * 3 + (0 if category == "Primary" else 100))


def contest_layout() -> list[list[tuple]]:
    pages: list[list[tuple]] = []
    for category, label in (("Primary", "Soalan"), ("Primary", "Problem"), ("Junior", "Problem")):
        for part_idx, (part, pts) in enumerate(PARTS):
            items: list[tuple] = [("heading", f"Part {part} ({pts} points each)")]
            for n in range(part_idx * 5 + 1, part_idx * 5 + 6):
                items.append(("problem", n, question_text(category, n)))
            pages.append(items)
    for category in ("Primary", "Junior"):
        pages.append([("heading", f"Answers {category}")] +
                     [("problem", n, answer_for(category, n)) for n in range(1, 21)])
    return pages


def contest_structure_dict() -> dict:
    parts = [{"name": f"Part {p}", "points": pts, "first_question": i * 5 + 1, "last_question": i * 5 + 5}
             for i, (p, pts) in enumerate(PARTS)]
    return {
        "sections": [
            {"category": "Primary", "language": "ms", "first_page": 1, "last_page": 4, "parts": parts},
            {"category": "Primary", "language": "en", "first_page": 5, "last_page": 8, "parts": parts},
            {"category": "Junior", "language": "en", "first_page": 9, "last_page": 12, "parts": parts},
        ],
        "answer_keys": [
            {"category": c, "page": 13 + i,
             "answers": [{"question": n, "answer": answer_for(c, n)} for n in range(1, 21)]}
            for i, c in enumerate(("Primary", "Junior"))
        ],
    }
