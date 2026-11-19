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
HEADER_FRAC = 0.07
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


def _anchor_in_line(line: list[tuple], left_margin: float) -> tuple[int, bool] | None:
    """(question number, labelled?) if this line starts a question."""
    first = line[0]
    if first[0] > left_margin + 12:
        return None
    t0 = first[4].strip()
    if t0.lower().rstrip(".:") in LABEL_WORDS and len(line) > 1:
        m = NUM_RE.match(line[1][4].strip())
        if m:
            return int(m.group(1)), True
    m = re.match(r"^(\d{1,3})[.)]$", t0)  # bare "12." at the left margin
    if m:
        return int(m.group(1)), False
    return None


def find_anchors(pdf_path: Path, pages: list[int]) -> list[Anchor]:
    found: list[tuple[Anchor, bool]] = []
    with fitz.open(pdf_path) as doc:
        for pno in sorted(pages):
            page = doc[pno - 1]
            lines = [ln for ln in _lines(page) if ln[0][1] < page.rect.height * FOOTER_FRAC]
            if not lines:
                continue
            left = min(ln[0][0] for ln in lines)
            for ln in lines:
                hit = _anchor_in_line(ln, left)
                if hit is not None:
                    found.append((Anchor(number=hit[0], page=pno, y=ln[0][1]), hit[1]))
    # If the paper labels its questions ("Question 12"), a line that merely starts with "13." is
    # part of a question's text, not a new question.
    if any(labelled for _, labelled in found):
        found = [f for f in found if f[1]]
    anchors: list[Anchor] = []
    for a, _ in found:
        if anchors and a.number <= anchors[-1].number:
            continue  # keep a strictly increasing sequence
        anchors.append(a)
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
                header_line = p2.rect.height * HEADER_FRAC
                above = [r for r in _content_rects(p2) if r.y1 <= first_bound + 1 and r.y0 >= header_line]
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


# ---- figures (diagrams/pictures) inside a question ----
MIN_FIG_W, MIN_FIG_H = 40.0, 30.0
THIN = 3.0  # lines thinner than this (fraction bars, rules, underlines) are not figures


def _gap(a: fitz.Rect, b: fitz.Rect) -> float:
    """How far apart two rectangles are (0 if they overlap)."""
    return max(0.0, b.x0 - a.x1, a.x0 - b.x1) + max(0.0, b.y0 - a.y1, a.y0 - b.y1)


def _merge(rects: list[fitz.Rect], gap: float = 6.0) -> list[fitz.Rect]:
    rects = [fitz.Rect(r) for r in rects]
    changed = True
    while changed:
        changed = False
        out: list[fitz.Rect] = []
        for r in rects:
            for i, o in enumerate(out):
                if (fitz.Rect(o.x0 - gap, o.y0 - gap, o.x1 + gap, o.y1 + gap)).intersects(r):
                    out[i] = o | r  # `o |= r` would build a new Rect and leave the list unchanged
                    changed = True
                    break
            else:
                out.append(fitz.Rect(r))
        rects = out
    return rects


def extract_figures(pdf_path: Path, boxes: list[list], out_dir: Path, prefix: str, dpi: int = 200) -> list[Path]:
    """Crop diagrams and embedded pictures that lie inside a question's crop boxes."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    with fitz.open(pdf_path) as doc:
        for page_no, x0, y0, x1, y1 in boxes:
            page = doc[int(page_no) - 1]
            clip = fitz.Rect(x0, y0, x1, y1)
            parts: list[fitz.Rect] = []
            for info in page.get_image_info():
                r = fitz.Rect(info["bbox"]) & clip
                if not r.is_empty and r.width * r.height > 400:
                    parts.append(r)
            for d in page.get_drawings():
                r = fitz.Rect(d["rect"])
                if r.width < THIN or r.height < THIN or not r.intersects(clip):
                    continue
                parts.append(r & clip)
            figs = [r for r in _merge(parts) if r.width >= MIN_FIG_W and r.height >= MIN_FIG_H]
            # pull in labels (A, B, 5 cm…) that sit on or just around the drawing
            words = page.get_text("words", clip=clip)
            for i in range(len(figs)):
                # nearest words first, so "5" joins before "cm" and pulls it in too
                base = figs[i]
                for w in sorted(words, key=lambda w: _gap(base, fitz.Rect(w[:4]))):
                    wr = fitz.Rect(w[:4])
                    f = figs[i]
                    if wr in fitz.Rect(f.x0 - 18, f.y0 - 18, f.x1 + 18, f.y1 + 18) and len(w[4]) <= 6:
                        figs[i] = f | wr
            for f in sorted(figs, key=lambda r: (round(r.y0), r.x0)):
                f = fitz.Rect(f.x0 - 3, f.y0 - 3, f.x1 + 3, f.y1 + 3) & page.rect
                p = out_dir / f"{prefix}-fig{len(paths) + 1}.png"
                page.get_pixmap(dpi=dpi, clip=f).save(str(p))
                paths.append(p)
    return paths
