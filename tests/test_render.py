import pymupdf as fitz
import pytest

from app.pdf.render import crop_box, crop_questions, find_anchors, has_text_layer, render_pages
from tests.fixtures.make_pdf import (SAMPLE_LAYOUT, SPANNING_LAYOUT, build_contest_pdf,
                                     build_image_only_pdf)


@pytest.fixture
def sample_pdf(tmp_path):
    return build_contest_pdf(tmp_path / "sample.pdf", SAMPLE_LAYOUT)


@pytest.fixture
def spanning_pdf(tmp_path):
    return build_contest_pdf(tmp_path / "span.pdf", SPANNING_LAYOUT)


@pytest.fixture
def image_only_pdf(tmp_path):
    return build_image_only_pdf(tmp_path / "scan.pdf")


def page_height(pdf, page):
    with fitz.open(pdf) as d:
        return d[page - 1].rect.height


def text_top(pdf, page, needle):
    with fitz.open(pdf) as d:
        return d[page - 1].search_for(needle)[0].y0


def footer_top(pdf, page):
    with fitz.open(pdf) as d:
        pg = d[page - 1]
        return min(b[1] for b in pg.get_text("blocks") if b[1] > pg.rect.height * 0.9)


def test_anchors_found_in_order(sample_pdf):
    assert [a.number for a in find_anchors(sample_pdf, [1, 2])] == [1, 2, 3, 4, 5, 6]


def test_anchors_only_on_requested_pages(sample_pdf):
    assert [a.number for a in find_anchors(sample_pdf, [3])] == [1, 2, 3]


def test_last_question_excludes_footer(sample_pdf, tmp_path):
    crops = crop_questions(sample_pdf, find_anchors(sample_pdf, [1]), tmp_path)
    assert crops[3][0].y1 < footer_top(sample_pdf, 1)


def test_part_heading_not_in_previous_crop(sample_pdf, tmp_path):
    crops = crop_questions(sample_pdf, find_anchors(sample_pdf, [2]), tmp_path)
    assert crops[5][0].y1 <= text_top(sample_pdf, 2, "Part B")


def test_question_spanning_pages_has_two_images(spanning_pdf, tmp_path):
    crops = crop_questions(spanning_pdf, find_anchors(spanning_pdf, [1, 2]), tmp_path)
    assert [c.page for c in crops[2]] == [1, 2]
    assert crops[2][1].y1 <= text_top(spanning_pdf, 2, "Problem 3")
    assert [c.page for c in crops[3]] == [2]


def test_crop_files_written(sample_pdf, tmp_path):
    crops = crop_questions(sample_pdf, find_anchors(sample_pdf, [1]), tmp_path / "out")
    assert all(c.path.exists() and c.path.suffix == ".png" for cs in crops.values() for c in cs)


def test_crop_contains_its_question_text(sample_pdf, tmp_path):
    crops = crop_questions(sample_pdf, find_anchors(sample_pdf, [1]), tmp_path)
    c = crops[2][0]
    with fitz.open(sample_pdf) as d:
        text = d[0].get_text(clip=fitz.Rect(c.x0, c.y0, c.x1, c.y1))
    assert "Problem 2." in text and "every 7 hours" in text and "Problem 3." not in text


def test_scanned_pdf_detected(image_only_pdf, sample_pdf):
    assert has_text_layer(image_only_pdf) is False
    assert has_text_layer(sample_pdf) is True


def test_render_pages_count(sample_pdf, tmp_path):
    pages = render_pages(sample_pdf, tmp_path)
    assert [p.name for p in pages] == ["page-001.png", "page-002.png", "page-003.png"]


def test_crop_box_writes_png(sample_pdf, tmp_path):
    out = crop_box(sample_pdf, 1, (50, 60, 500, 120), tmp_path / "x.png")
    assert out.exists()


def test_question_label_variants(tmp_path):
    pdf = build_contest_pdf(tmp_path / "q.pdf", [[("problem", 1, "a"), ("problem", 2, "b")]], label="Question")
    assert [a.number for a in find_anchors(pdf, [1])] == [1, 2]


def test_last_question_trimmed_to_content(sample_pdf, tmp_path):
    crops = crop_questions(sample_pdf, find_anchors(sample_pdf, [1]), tmp_path)
    with fitz.open(sample_pdf) as d:
        bottom = d[0].search_for("Find angle APC")[0].y1
    assert crops[3][0].y1 - bottom < 20


def _text_pdf(tmp_path, lines):
    import pymupdf as fitz
    doc = fitz.open()
    page = doc.new_page()
    y = 80
    for text in lines:
        page.insert_text((72, y), text, fontsize=11)
        y += 22
    path = tmp_path / "t.pdf"
    doc.save(path)
    return path


def test_bare_number_line_inside_labelled_question_is_not_an_anchor(tmp_path):
    # SASMO 2019 G8 Q12 wraps so that a line starts with "13." before the real "Question 13"
    from app.pdf.render import find_anchors
    pdf = _text_pdf(tmp_path, ["Question 12", "Find the value of [x]. For example, [13.54] =", "13.",
                               "A. 69", "B. 70", "Question 13", "Which fraction is largest?"])
    assert [a.number for a in find_anchors(pdf, [1])] == [12, 13]
    a13 = find_anchors(pdf, [1])[1]
    assert a13.y > 80 + 4 * 22  # the "Question 13" line, not the stray "13."


def test_bare_numbers_still_work_without_labels(tmp_path):
    from app.pdf.render import find_anchors
    pdf = _text_pdf(tmp_path, ["1. What is 2+2?", "2. What is 3+3?", "3. What is 4+4?"])
    assert [a.number for a in find_anchors(pdf, [1])] == [1, 2, 3]
