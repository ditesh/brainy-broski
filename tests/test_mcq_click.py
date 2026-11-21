"""Multiple choice: he taps the option itself instead of reading it and then pressing a letter."""
import re

from app.models import AnswerType, Attempt
from app.practice.service import start_attempt
from app.web import question_html

TEXT = "What is $2+3$?\n\n(A) 4\n(B) 5\n(C) 6\n(D) 7\n(E) 8"


def test_options_become_answer_buttons():
    html = str(question_html(TEXT, [], choose={"form": "answer-form", "selected": "B"}))
    buttons = re.findall(r'<button[^>]*class="mcq-choice[^"]*"[^>]*>', html)
    assert len(buttons) == 5
    assert all('name="answer"' in b and 'form="answer-form"' in b for b in buttons)
    assert [re.search(r'value="(\w)"', b).group(1) for b in buttons] == list("ABCDE")
    assert 'value="B"' in next(b for b in buttons if "selected" in b)


def test_plain_display_unchanged():
    assert "<button" not in str(question_html(TEXT, []))


def _mcq_attempt(db, child, paper, text, show_original=None):
    q = next(q for q in paper.questions if q.number == 1)
    q.problem.answer_type, q.problem.transcription, q.problem.answer = AnswerType.mcq, text, "B"
    q.show_original = show_original
    db.commit()
    return start_attempt(db, child, paper, "practice", [1, 2])


def test_attempt_page_uses_clickable_options(child_client, db, child, junior_paper):
    a = _mcq_attempt(db, child, junior_paper, TEXT)
    html = child_client.get(f"/attempts/{a.id}?q=1").text
    assert html.count('class="mcq-choice') == 5
    assert 'class="mcq"' not in html                       # no separate A–E row


def test_tapping_an_option_saves_it(child_client, db, child, junior_paper):
    a = _mcq_attempt(db, child, junior_paper, TEXT)
    r = child_client.post(f"/attempts/{a.id}/answer", data={"q": "1", "answer": "B", "go": "2"},
                          follow_redirects=False)
    assert r.status_code == 303
    db.expire_all()
    assert db.get(Attempt, a.id).responses[0].first_answer == "B"
    assert 'mcq-choice selected' in child_client.get(f"/attempts/{a.id}?q=1").text


def test_picture_questions_keep_letter_buttons(child_client, db, child, junior_paper):
    a = _mcq_attempt(db, child, junior_paper, TEXT, show_original=True)
    html = child_client.get(f"/attempts/{a.id}?q=1").text
    assert 'class="mcq"' in html and "mcq-choice" not in html


def test_options_not_in_text_keep_letter_buttons(child_client, db, child, junior_paper):
    a = _mcq_attempt(db, child, junior_paper, "Which net folds into the cube shown?")
    html = child_client.get(f"/attempts/{a.id}?q=1").text
    assert 'class="mcq"' in html and "mcq-choice" not in html
