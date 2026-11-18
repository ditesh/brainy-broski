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


def test_missing_api_key_is_a_clear_ai_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    with pytest.raises(AIError, match="API key"):
        AnthropicAIClient(None, "m").structured(ReferenceSolution, "s", [], "t", "low")


# ---- clearer errors ----

def _status_error(code, body=None, msg="boom"):
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx.Response(code, request=req, json=body or {})
    return anthropic.APIStatusError(msg, response=resp, body=body)


def test_ignores_stray_anthropic_base_url(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://openrouter.ai/api")
    with patch("app.ai.client.anthropic.Anthropic") as cls:
        AnthropicAIClient("k", "m")
        assert cls.call_args.kwargs["base_url"] == "https://api.anthropic.com"


def test_custom_base_url_respected():
    with patch("app.ai.client.anthropic.Anthropic") as cls:
        AnthropicAIClient("k", "m", base_url="https://proxy.example")
        assert cls.call_args.kwargs["base_url"] == "https://proxy.example"


@pytest.mark.parametrize("code,body,expected", [
    (401, {"error": {"message": "Invalid API key"}}, "API key was rejected"),
    (403, None, "not allowed"),
    (400, {"error": {"message": "Your credit balance is too low to access the Anthropic API."}}, "out of credit"),
    (402, None, "out of credit"),
    (404, {"error": {"message": "model: claude-x"}}, "model"),
    (413, None, "too big"),
    (429, None, "busy"),
    (529, None, "busy"),
    (500, None, "problem on Claude's side"),
])
def test_friendly_status_messages(mock_sdk, code, body, expected):
    mock_sdk.messages.parse.side_effect = _status_error(code, body)
    with pytest.raises(AIError) as e:
        AnthropicAIClient("k", "m").structured(ReferenceSolution, "s", [], "t", "low")
    msg = str(e.value)
    assert expected in msg and "{" not in msg


def test_connection_message(mock_sdk):
    mock_sdk.messages.parse.side_effect = anthropic.APIConnectionError(request=httpx.Request("POST", "https://x"))
    with pytest.raises(AIError, match="Couldn't reach Claude"):
        AnthropicAIClient("k", "m").structured(ReferenceSolution, "s", [], "t", "low")


def test_failed_diagnosis_reason_shown_to_parent_only(parent_client, child_client, db, junior_paper, child, parent,
                                                      fake_ai, settings):
    from app.ai.schemas import ReferenceSolution as RS
    from app.diagnosis.service import diagnose_response
    from app.practice.service import save_answer, start_attempt, submit, submit_retry
    a = start_attempt(db, child, junior_paper, "practice", [2])
    save_answer(db, a, 2, "5")
    submit(db, a)
    r = a.responses[0]
    submit_retry(db, r, "6")
    fake_ai.add(RS, AIError("Claude is busy right now. Try again in a minute."))
    diagnose_response(db, r.id, fake_ai, settings)
    assert "Claude is busy" in parent_client.get(f"/responses/{r.id}/feedback").text
    assert "Claude is busy" not in child_client.get(f"/responses/{r.id}/feedback").text
