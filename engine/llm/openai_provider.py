from __future__ import annotations

import os
from pathlib import Path

from ..util import image_payload
from .base import LLMProvider, ProviderError


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self._client = None

    def available(self) -> bool:
        return bool(os.getenv("OPENAI_API_KEY"))

    def describe(self) -> dict:
        return {"name": self.name, "model": self.cfg.get("model", "gpt-5"), "configured": self.available()}

    def client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(timeout=float(self.cfg.get("timeout", 600)))
        return self._client

    def complete(self, system, prompt, images=None, json_schema=None, max_tokens=16000) -> str:
        import openai

        content: list[dict] = [{"type": "text", "text": prompt}]
        for p in images or []:
            b64, mt = image_payload(Path(p))
            content.append({"type": "image_url", "image_url": {"url": f"data:{mt};base64,{b64}"}})
        kwargs: dict = {}
        if json_schema is not None:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            resp = self.client().chat.completions.create(
                model=self.cfg.get("model", "gpt-5"),
                messages=[{"role": "system", "content": system}, {"role": "user", "content": content}],
                max_completion_tokens=max_tokens,
                **kwargs,
            )
        except openai.APIError as e:
            raise ProviderError(f"openai: {e}") from e
        choice = resp.choices[0]
        if choice.finish_reason == "length":
            raise ProviderError("openai: reply truncated (max tokens)")
        return choice.message.content or ""
