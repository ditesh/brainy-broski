"""Render PDF pages and crop individual questions using the PDF's text layer.

All page numbers are 1-based. Coordinates are PDF points (origin top-left).
"""
import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf as fitz

LABEL_WORDS = {"problem", "question", "soalan", "q"}
NUM_RE = re.compile(r"^(\d{1,3})[.):]?$")
CUT_RE = re.compile(r"^(part|section|bahagian)\s+[A-Z]\b", re.IGNORECASE)
FOOTER_FRAC = 0.92
PAD = 4.0


@dataclass(frozen=True)
class Anchor:
    number: int
    page: int
    y: float


@dataclass(frozen=True)
class CropBox:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    path: Path

    def as_list(self) -> list:
        return [self.page, self.x0, self.y0, self.x1, self.y1]


def render_pages(pdf_path: Path, out_dir: Path, dpi: int = 150) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc, start=1):
            p = out_dir / f"page-{i:03}.png"
            page.get_pixmap(dpi=dpi).save(str(p))
            paths.append(p)
    return paths


def has_text_layer(pdf_path: Path) -> bool:
    with fitz.open(pdf_path) as doc:
        return any(page.get_text("text").strip() for page in doc)


def _lines(page: fitz.Page) -> list[list[tuple]]:
    """Words grouped by (block, line), each line in reading order."""
    groups: dict[tuple[int, int], list[tuple]] = {}
    for w in page.get_text("words"):
        groups.setdefault((w[5], w[6]), []).append(w)
    lines = [sorted(ws, key=lambda w: w[0]) for ws in groups.values()]
    lines.sort(key=lambda ws: (round(ws[0][1], 1), ws[0][0]))
    return lines


def _anchor_in_line(line: list[tuple], left_margin: float) -> int | None:
    first = line[0]
    if first[0] > left_margin + 12:
        return None
    t0 = first[4].strip()
    if t0.lower().rstrip(".:") in LABEL_WORDS and len(line) > 1:
        m = NUM_RE.match(line[1][4].strip())
        if m:
            return int(m.group(1))
    m = re.match(r"^(\d{1,3})[.)]$", t0)  # bare "12." at the left margin
    if m:
        return int(m.group(1))
    return None


def find_anchors(pdf_path: Path, pages: list[int]) -> list[Anchor]:
    anchors: list[Anchor] = []
    with fitz.open(pdf_path) as doc:
        for pno in sorted(pages):
            page = doc[pno - 1]
            lines = [ln for ln in _lines(page) if ln[0][1] < page.rect.height * FOOTER_FRAC]
            if not lines:
                continue
            left = min(ln[0][0] for ln in lines)
            for ln in lines:
                n = _anchor_in_line(ln, left)
                if n is None:
                    continue
                if anchors and n <= anchors[-1].number:
                    continue  # keep a strictly increasing sequence
                anchors.append(Anchor(number=n, page=pno, y=ln[0][1]))
    return anchors


def _footer_top(page: fitz.Page) -> float:
    limit = page.rect.height * FOOTER_FRAC
    tops = [b[1] for b in page.get_text("blocks") if b[1] >= limit]
    return min(tops) if tops else page.rect.height


def find_cut_lines(pdf_path: Path, page_no: int) -> list[float]:
    with fitz.open(pdf_path) as doc:
        return _cut_lines(doc[page_no - 1])


def _cut_lines(page: fitz.Page) -> list[float]:
    cuts = []
    for ln in _lines(page):
        text = " ".join(w[4] for w in ln)
        if CUT_RE.match(text):
            cuts.append(ln[0][1])
    cuts.append(_footer_top(page))
    return sorted(cuts)


def _content_rects(page: fitz.Page) -> list[fitz.Rect]:
    limit = _footer_top(page)
    rects = []
    for _kind, r in page.get_bboxlog():
        rect = fitz.Rect(r)
        if rect.is_empty or rect.y0 >= limit - 1:
            continue
        if rect.width >= page.rect.width * 0.98 and rect.height >= page.rect.height * 0.98:
            continue  # full-page background
        rects.append(rect)
    return rects


def _x_extent(page: fitz.Page) -> tuple[float, float]:
    rects = _content_rects(page)
    if not rects:
        return 36.0, page.rect.width - 36.0
    x0 = max(0.0, min(r.x0 for r in rects) - 8)
    x1 = min(page.rect.width, max(r.x1 for r in rects) + 8)
    return x0, x1


def _save_clip(page: fitz.Page, rect: fitz.Rect, out: Path, dpi: int) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    page.get_pixmap(dpi=dpi, clip=rect).save(str(out))


def crop_questions(pdf_path: Path, anchors: list[Anchor], out_dir: Path, dpi: int = 150) -> dict[int, list[CropBox]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    allowed_pages = {a.page for a in anchors}
    if anchors:
        allowed_pages |= set(range(min(allowed_pages), max(allowed_pages) + 2))
    result: dict[int, list[CropBox]] = {}
    with fitz.open(pdf_path) as doc:
        for i, a in enumerate(anchors):
            nxt = anchors[i + 1] if i + 1 < len(anchors) else None
            page = doc[a.page - 1]
            boxes: list[tuple[int, float, float]] = []
            stops = [y for y in _cut_lines(page) if y > a.y + 1]
            if nxt and nxt.page == a.page:
                stops.append(nxt.y)
            end = min(stops) - 2
            inside = [r.y1 for r in _content_rects(page) if r.y0 >= a.y - PAD - 1 and r.y1 <= end + 1]
            if inside:
                end = min(end, max(inside) + PAD)
            boxes.append((a.page, a.y - PAD, end))
            # continuation onto the next page?
            if (nxt is None or nxt.page > a.page) and a.page < doc.page_count and (a.page + 1) in allowed_pages:
                p2 = doc[a.page]
                bounds = list(_cut_lines(p2))
                if nxt and nxt.page == a.page + 1:
                    bounds.append(nxt.y)
                first_bound = min(bounds)
                above = [r for r in _content_rects(p2) if r.y1 <= first_bound + 1]
                if above and (nxt is not None and nxt.page == a.page + 1):
                    top = min(r.y0 for r in above)
                    if top < first_bound - 5:
                        boxes.append((a.page + 1, top - PAD, first_bound - 2))
            crops = []
            for k, (pno, y0, y1) in enumerate(boxes):
                pg = doc[pno - 1]
                x0, x1 = _x_extent(pg)
                path = out_dir / f"q{a.number:03}-{k}.png"
                _save_clip(pg, fitz.Rect(x0, max(0, y0), x1, y1), path, dpi)
                crops.append(CropBox(pno, x0, max(0, y0), x1, y1, path))
            result[a.number] = crops
    return result


def crop_box(pdf_path: Path, page_no: int, box: tuple[float, float, float, float], out_path: Path,
             dpi: int = 150) -> Path:
    with fitz.open(pdf_path) as doc:
        _save_clip(doc[page_no - 1], fitz.Rect(*box), out_path, dpi)
    return out_path
