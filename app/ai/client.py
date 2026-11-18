import base64
from pathlib import Path
from typing import Protocol, TypeVar

import anthropic
from fastapi import Request

T = TypeVar("T")

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


class AnthropicAIClient:
    def __init__(self, api_key: str | None, model: str):
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
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
            raise AIError(str(e)) from e
        if resp.stop_reason == "refusal":
            raise AIRefusal("Claude declined this request")
        if resp.parsed_output is None:
            raise AIError(f"No structured output (stop_reason={resp.stop_reason})")
        return resp.parsed_output


def get_ai(request: Request) -> AIClient:
    ai = getattr(request.app.state, "ai", None)
    if ai is None:
        s = request.app.state.settings
        ai = AnthropicAIClient(s.anthropic_api_key, s.claude_model)
        request.app.state.ai = ai
    return ai
