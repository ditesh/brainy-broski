import re
from fractions import Fraction

from app.models import AnswerType

_INT_STRIP = re.compile(r"[\s,_]")


def normalise(raw: str | None, answer_type: AnswerType) -> str | None:
    """Canonical string form of an answer, or None if empty/unparseable."""
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    if answer_type == AnswerType.integer:
        s = _INT_STRIP.sub("", s)
        if s.startswith("+"):
            s = s[1:]
        if not re.fullmatch(r"-?\d+", s):
            return None
        return str(int(s))
    if answer_type == AnswerType.fraction:
        mixed = re.fullmatch(r"(-?)(\d+)\s+(\d+)\s*/\s*(\d+)", s)
        if mixed:
            sign, whole, num, den = mixed.groups()
            if int(den) == 0:
                return None
            value = int(whole) + Fraction(int(num), int(den))
            return str(-value if sign else value)
        s = re.sub(r"\s", "", s)
        try:
            return str(Fraction(s))
        except (ValueError, ZeroDivisionError):
            return None
    if answer_type == AnswerType.mcq:
        s = s.strip("() ").upper()
        return s if re.fullmatch(r"[A-E]", s) else None
    return " ".join(s.split()).casefold()


def is_correct(given: str | None, official: str, answer_type: AnswerType) -> bool:
    g = normalise(given, answer_type)
    o = normalise(official, answer_type)
    return g is not None and o is not None and g == o
