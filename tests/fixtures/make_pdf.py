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
