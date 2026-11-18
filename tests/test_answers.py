import pytest

from app.answers import is_correct, normalise
from app.models import AnswerType


@pytest.mark.parametrize("given", ["11111111100", "11 111 111 100", "11,111,111,100", "011111111100"])
def test_big_integer_forms(given):
    assert is_correct(given, "11111111100", AnswerType.integer)


def test_plus_sign():
    assert is_correct("+5", "5", AnswerType.integer)


def test_negative_integer():
    assert is_correct("-3", "-3", AnswerType.integer)
    assert not is_correct("3", "-3", AnswerType.integer)


def test_zero_forms():
    assert is_correct("000", "0", AnswerType.integer)


def test_wrong_integer():
    assert not is_correct("54", "56", AnswerType.integer)


def test_garbage_integer_is_wrong_not_error():
    assert not is_correct("abc", "5", AnswerType.integer)


@pytest.mark.parametrize("given", ["1/2", "2/4", "0.5", " 1 / 2 "])
def test_fraction_equivalents(given):
    assert is_correct(given, "1/2", AnswerType.fraction)


def test_fraction_divide_by_zero_is_wrong():
    assert not is_correct("1/0", "1/2", AnswerType.fraction)


@pytest.mark.parametrize("given", ["b", "B", "(b)", " B "])
def test_mcq_forms(given):
    assert is_correct(given, "B", AnswerType.mcq)


def test_mcq_out_of_range():
    assert normalise("F", AnswerType.mcq) is None


def test_empty_is_none():
    assert normalise("  ", AnswerType.integer) is None


def test_text_casefold():
    assert is_correct("  Monday ", "monday", AnswerType.text)
