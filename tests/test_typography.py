import re
from pathlib import Path

CSS = Path("app/static/app.css").read_text()
TEMPLATES = list(Path("app/templates").glob("*.html"))


def _rules_outside_root():
    return re.sub(r":root\s*\{[^}]*\}", "", CSS)


def test_type_scale_tokens_defined():
    for token in ("--fs-xs", "--fs-sm", "--fs-md", "--fs-lg", "--fs-xl", "--fs-2xl", "--fs-3xl",
                  "--fw-regular", "--fw-bold", "--fw-heavy", "--fw-black", "--font-ui", "--font-mono"):
        assert token + ":" in CSS, token


def test_font_sizes_use_tokens():
    bad = [m for m in re.findall(r"font-size:\s*([^;]+);", _rules_outside_root()) if not m.strip().startswith("var(--fs-")]
    assert bad == []


def test_font_weights_use_tokens():
    bad = [m for m in re.findall(r"font-weight:\s*([^;]+);", _rules_outside_root()) if not m.strip().startswith("var(--fw-")]
    assert bad == []


def test_font_families_use_tokens():
    rules = _rules_outside_root()
    fams = re.findall(r"font-family:\s*([^;]+);", rules) + re.findall(r"\bfont:\s*([^;]+);", rules)
    assert all("var(--font-" in f or f.strip() == "inherit" for f in fams), fams


def test_no_inline_font_styles_in_templates():
    offenders = [t.name for t in TEMPLATES if re.search(r'style="[^"]*font', t.read_text())]
    assert offenders == []
