import base64
import logging
from pathlib import Path
from typing import Protocol, TypeVar

import anthropic
from fastapi import Request

T = TypeVar("T")
log = logging.getLogger(__name__)
ANTHROPIC_API_URL = "https://api.anthropic.com"

MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".gif": "image/gif", ".webp": "image/webp"}


class AIError(Exception):
    """A Claude call failed (network, API error, or no usable output)."""


class AIRefusal(AIError):
    """Claude declined the request (stop_reason == 'refusal')."""


class AIClient(Protocol):
    def structured(self, schema: type[T], system: str, images: list[Path], text: str, effort: str) -> T: ...


def _image_block(path: Path) -> dict:
    data = base64.standard_b64encode(Path(path).read_bytes()).decode("ascii")
    media = MEDIA_TYPES.get(Path(path).suffix.lower(), "image/png")
    return {"type": "image", "source": {"type": "base64", "media_type": media, "data": data}}


def _api_message(e: anthropic.APIStatusError) -> str:
    body = e.body if isinstance(e.body, dict) else {}
    err = body.get("error") if isinstance(body.get("error"), dict) else body
    return str(err.get("message") or e.message or "")


def friendly_error(e: Exception) -> str:
    """One plain sentence for the parent; the raw error goes to the log."""
    if isinstance(e, anthropic.APITimeoutError):
        return "Claude took too long to answer. Try again."
    if isinstance(e, anthropic.APIConnectionError):
        return "Couldn't reach Claude. Check the internet connection and try again."
    if isinstance(e, anthropic.APIStatusError):
        code, text = e.status_code, _api_message(e).lower()
        if code == 401:
            return "The Claude API key was rejected. Check ANTHROPIC_API_KEY in the .env file."
        if code == 402 or "credit balance" in text or "billing" in text:
            return "The Claude account is out of credit. Add credit at console.anthropic.com, then try again."
        if code == 403:
            return "This API key is not allowed to use Claude for this. Check the key's permissions."
        if code == 404:
            return "Claude couldn't find the model set in CLAUDE_MODEL. Check that setting."
        if code == 413:
            return "This request was too big for Claude (the paper may have too many pages)."
        if code == 429 or code == 529:
            return "Claude is busy right now. Try again in a minute."
        if code >= 500:
            return "There was a problem on Claude's side. Try again in a minute."
        return f"Claude couldn't handle this request (error {code})."
    return "Something went wrong talking to Claude. Try again."


class AnthropicAIClient:
    def __init__(self, api_key: str | None, model: str, base_url: str = ANTHROPIC_API_URL):
        # base_url is passed explicitly so a stray ANTHROPIC_BASE_URL (e.g. set for another tool) is ignored
        self._client = anthropic.Anthropic(api_key=api_key, base_url=base_url) if api_key \
            else anthropic.Anthropic(base_url=base_url)
        self.model = model

    def structured(self, schema, system, images, text, effort):
        content = [_image_block(p) for p in images] + [{"type": "text", "text": text}]
        try:
            resp = self._client.messages.parse(
                model=self.model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": content}],
                output_format=schema,
                output_config={"effort": effort},
            )
        except anthropic.APIError as e:  # includes connection, status and timeout errors
            log.warning("Claude API error: %r", e)
            raise AIError(friendly_error(e)) from e
        except TypeError as e:  # raised by the SDK when no credentials are configured
            if "authentication" in str(e).lower():
                raise AIError("The Claude API key is not set (ANTHROPIC_API_KEY).") from e
            raise
        if resp.stop_reason == "refusal":
            raise AIRefusal("Claude declined this request")
        if resp.parsed_output is None:
            raise AIError(f"No structured output (stop_reason={resp.stop_reason})")
        return resp.parsed_output


def ensure_ai(app) -> AIClient:
    ai = getattr(app.state, "ai", None)
    if ai is None:
        s = app.state.settings
        ai = AnthropicAIClient(s.anthropic_api_key, s.claude_model, s.claude_base_url)
        app.state.ai = ai
    return ai


def get_ai(request: Request) -> AIClient:
    return ensure_ai(request.app)
