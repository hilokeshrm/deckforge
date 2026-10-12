from __future__ import annotations

import os
from pathlib import Path

from ..util import image_payload
from .base import LLMProvider, ProviderError


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self._client = None

    def available(self) -> bool:
        return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))

    def describe(self) -> dict:
        return {"name": self.name, "model": self.cfg.get("model", "claude-opus-5-5"), "configured": self.available()}

    def client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    def complete(self, system, prompt, images=None, json_schema=None, max_tokens=16000) -> str:
        import anthropic

        content: list[dict] = []
        for p in images or []:
            b64, mt = image_payload(Path(p))
            content.append({"type": "image", "source": {"type": "base64", "media_type": mt, "data": b64}})
        content.append({"type": "text", "text": prompt})
        params = dict(
            model=self.cfg.get("model", "claude-opus-5-5"),
            max_tokens=max(int(self.cfg.get("max_tokens", 32000)), max_tokens),
            system=system,
            messages=[{"role": "user", "content": content}],
            output_config={"effort": self.cfg.get("effort", "high")},
        )
        try:
            # Streaming avoids HTTP timeouts on long deck JSON outputs.
            if self.cfg.get("refusal_fallback", True):
                with self.client().beta.messages.stream(
                    **params, betas=["server-side-fallback-2026-07-01"], fallbacks="default"
                ) as stream:
                    msg = stream.get_final_message()
            else:
                with self.client().messages.stream(**params) as stream:
                    msg = stream.get_final_message()
        except anthropic.APIStatusError as e:
            raise ProviderError(f"anthropic HTTP {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise ProviderError(f"anthropic connection error: {e}") from e
        if msg.stop_reason == "refusal":
            raise ProviderError("anthropic declined the request")
        if msg.stop_reason == "max_tokens":
            raise ProviderError("anthropic reply truncated (max_tokens)")
        return "".join(b.text for b in msg.content if b.type == "text")
