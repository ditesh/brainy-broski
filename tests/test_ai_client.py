from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import anthropic
import httpx
import pytest
from PIL import Image

from app.ai.client import AIError, AIRefusal, AnthropicAIClient
from app.ai.schemas import QuestionAnalysis, ReferenceSolution


@pytest.fixture
def tmp_png(tmp_path):
    p = tmp_path / "q.png"
    Image.new("RGB", (10, 10), "white").save(p)
    return p


@pytest.fixture
def mock_sdk():
    with patch("app.ai.client.anthropic.Anthropic") as cls:
        sdk = MagicMock()
        cls.return_value = sdk
        sdk.messages.parse.return_value = SimpleNamespace(
            stop_reason="end_turn", parsed_output=ReferenceSolution(steps=["a"], final_answer="4"))
        yield sdk


def test_images_sent_before_text(mock_sdk, tmp_png):
    out = AnthropicAIClient("k", "claude-opus-5-5").structured(ReferenceSolution, "sys", [tmp_png], "solve", "high")
    kw = mock_sdk.messages.parse.call_args.kwargs
    content = kw["messages"][0]["content"]
    assert [b["type"] for b in content] == ["image", "text"]
    assert content[0]["source"]["media_type"] == "image/png"
    assert kw["model"] == "claude-opus-5-5" and kw["output_format"] is ReferenceSolution
    assert kw["output_config"] == {"effort": "high"} and kw["system"] == "sys"
    assert out.final_answer == "4"


def test_jpeg_media_type(mock_sdk, tmp_path):
    p = tmp_path / "w.jpg"
    Image.new("RGB", (10, 10)).save(p)
    AnthropicAIClient("k", "m").structured(ReferenceSolution, "s", [p], "t", "low")
    assert mock_sdk.messages.parse.call_args.kwargs["messages"][0]["content"][0]["source"]["media_type"] == "image/jpeg"


def test_refusal_raises(mock_sdk):
    mock_sdk.messages.parse.return_value = SimpleNamespace(stop_reason="refusal", parsed_output=None)
    with pytest.raises(AIRefusal):
        AnthropicAIClient("k", "m").structured(ReferenceSolution, "s", [], "t", "low")


def test_missing_output_raises(mock_sdk):
    mock_sdk.messages.parse.return_value = SimpleNamespace(stop_reason="max_tokens", parsed_output=None)
    with pytest.raises(AIError):
        AnthropicAIClient("k", "m").structured(ReferenceSolution, "s", [], "t", "low")


def test_api_error_wrapped(mock_sdk):
    mock_sdk.messages.parse.side_effect = anthropic.APIConnectionError(request=httpx.Request("POST", "https://x"))
    with pytest.raises(AIError):
        AnthropicAIClient("k", "m").structured(ReferenceSolution, "s", [], "t", "low")


def test_unknown_tags_dropped():
    q = QuestionAnalysis(transcription="x", answer_type="integer", tags=["parity", "nonsense"])
    assert q.tags == ["parity"]


def test_tags_capped_at_three():
    q = QuestionAnalysis(transcription="x", answer_type="integer",
                         tags=["parity", "algebra", "areas", "logic"])
    assert q.tags == ["parity", "algebra", "areas"]
