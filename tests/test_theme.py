import pytest

from app.practice.service import save_answer, start_attempt, submit


def test_fun_font_and_brand(client):
    html = client.get("/login").text
    assert "fonts.googleapis.com/css2?family=Nunito" in html
    assert 'class="brand"' in html and "/static/favicon.svg" in html


def test_practice_home_is_friendly(child_client, junior_paper):
    html = child_client.get("/practice").text
    assert "Hi Kid" in html and "Pick a challenge" in html


@pytest.mark.parametrize("answers,stars,confetti", [
    ({n: "x" for n in range(1, 6)}, 0, False),
    ({1: "18", 2: "21", 3: "24", 4: "27", 5: "x"}, 2, False),
    ({1: "18", 2: "21", 3: "24", 4: "27", 5: "30"}, 3, True),
])
def test_results_show_stars_and_confetti(child_client, db, junior_paper, child, answers, stars, confetti):
    a = start_attempt(db, child, junior_paper, "practice", [1, 2, 3, 4, 5])
    for n, v in answers.items():
        save_answer(db, a, n, v)
    submit(db, a)
    html = child_client.get(f"/attempts/{a.id}/results").text
    assert html.count('class="star on"') == stars
    assert ("data-confetti" in html) == confetti


def test_label_chips_have_emoji(child_client, db, junior_paper, child, parent):
    from app.models import DiagnosisStatus, Label
    a = start_attempt(db, child, junior_paper, "practice", [2])
    save_answer(db, a, 2, "5")
    submit(db, a)
    r = a.responses[0]
    r.retry_answer, r.correct_retry = "6", False
    p = r.paper_question.problem
    p.verified, p.reference_solution = True, "1. x"
    r.label, r.diagnosis_status = Label.technique, DiagnosisStatus.done
    r.diagnosis = {"label": "technique", "technique_tag": "parity", "hint": "h", "explanation": "e"}
    db.commit()
    assert "🧠" in child_client.get(f"/responses/{r.id}/feedback").text


def test_links_not_underlined_until_hover():
    import re
    from pathlib import Path
    css = Path("app/static/app.css").read_text()
    base = re.search(r"(?m)^a \{([^}]*)\}", css).group(1)
    assert "text-decoration: none" in base
    assert re.search(r"a:hover[^{]*\{[^}]*text-decoration: underline", css)
    assert re.search(r"a:focus-visible[^{]*\{[^}]*text-decoration: underline", css)


def test_select_uses_custom_centred_arrow():
    import re
    from pathlib import Path
    css = Path("app/static/app.css").read_text()
    rule = re.search(r"(?m)^select \{([^}]*)\}", css).group(1)
    assert "appearance: none" in rule and "50%" in rule and "padding-right" in rule
