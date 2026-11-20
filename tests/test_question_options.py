"""Multiple-choice options show one per line, however the transcription laid them out."""
import re

from app.web import question_html


def _items(html):
    m = re.search(r'<ul class="mcq-options">(.*?)</ul>', str(html), re.S)
    assert m, html
    return [re.sub(r"<[^>]+>", "", li).strip() for li in re.findall(r"<li>(.*?)</li>", m.group(1), re.S)]


def test_options_on_separate_lines():
    text = "Evaluate $9+8$.\n\n(A) 955\n(B) 2019\n(C) 2034\n(D) 3216\n(E) None of the above"
    assert _items(question_html(text, [])) == ["(A) 955", "(B) 2019", "(C) 2034", "(D) 3216", "(E) None of the above"]


def test_options_all_on_one_line():
    text = "Evaluate it.\n\n(A) 955 (B) 2019 (C) 2034 (D) 3216 (E) None of the above"
    assert _items(question_html(text, [])) == ["(A) 955", "(B) 2019", "(C) 2034", "(D) 3216", "(E) None of the above"]


def test_options_straight_after_the_question():
    text = "Evaluate it.\n(A) 1\n(B) 2"
    html = str(question_html(text, []))
    assert "Evaluate it." in html and _items(html) == ["(A) 1", "(B) 2"]


def test_maths_in_options_kept_for_katex():
    html = str(question_html("Pick one.\n\n(A) $\\frac{1}{2}$\n(B) $3 < 4$", []))
    assert "$\\frac{1}{2}$" in html and "$3 &lt; 4$" in html


def test_letters_mid_sentence_are_not_options():
    text = "Which is bigger, (A) or (B)? Choose the larger."
    assert "mcq-options" not in str(question_html(text, []))


def test_figures_still_placed_with_options():
    text = "Look at the picture.\n\n[[figure]]\n\n(A) 1\n(B) 2"
    html = str(question_html(text, ["crops/1/q.png"]))
    assert html.index('src="/files/crops/1/q.png"') < html.index("mcq-options")


def test_picture_options_with_figure_markers():
    text = "Which net?\n\n(A) [[figure]]\n(B) [[figure]]"
    html = str(question_html(text, []))  # markers inside options are left as text when no pictures
    assert "mcq-options" in html


def test_single_option_line_keeps_paragraphs():
    html = str(question_html("Note:\n(A) is a label here.\n\nNext paragraph.", []))
    assert "mcq-options" not in html and "<p>Next paragraph.</p>" in html
