"""Local models on the GPU through the Ollama HTTP API."""
from __future__ import annotations

from pathlib import Path

import requests

from ..gpu import ollama_tags, pick_models
from ..util import image_payload, log
from .base import LLMProvider, ProviderError


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self.url = self.cfg.get("url", "http://localhost:11434").rstrip("/")
        self._models: dict | None = None

    def models(self) -> dict:
        if self._models is None:
            text = self.cfg.get("text_model", "auto")
            vision = self.cfg.get("vision_model", "auto")
            if "auto" in (text, vision):
                picked = pick_models()
                log.info("GPU VRAM %.1f GB -> text=%s vision=%s", picked["vram_gb"], picked["text"], picked["vision"])
                text = picked["text"] if text == "auto" else text
                vision = picked["vision"] if vision == "auto" else vision
            self._models = {"text": text, "vision": vision}
        return self._models

    def available(self) -> bool:
        try:
            return requests.get(self.url + "/api/version", timeout=3).ok
        except requests.RequestException:
            return False

    def describe(self) -> dict:
        return {"name": self.name, "url": self.url, **self.models(), "installed": ollama_tags(self.url)}

    def complete(self, system, prompt, images=None, json_schema=None, max_tokens=16000) -> str:
        model = self.models()["vision" if images else "text"]
        user: dict = {"role": "user", "content": prompt}
        if images:
            side = int(self.cfg.get("max_image_side", 1280))
            user["images"] = [image_payload(Path(p), side)[0] for p in images]
        body: dict = {
            "model": model,
            "messages": [{"role": "system", "content": system}, user],
            "stream": False,
            "keep_alive": self.cfg.get("keep_alive", "30m"),
            "options": {
                "num_ctx": int(self.cfg.get("num_ctx", 16384)),
                "num_gpu": int(self.cfg.get("num_gpu", 999)),  # keep every layer on the GPU
                "temperature": float(self.cfg.get("temperature", 0.4)),
                "num_predict": int(max_tokens),
            },
        }
        if json_schema is not None:
            body["format"] = json_schema  # Ollama structured outputs (grammar-constrained)
        think = self.cfg.get("think")
        if think is not None and not images:
            body["think"] = bool(think)
        return self._post(body)

    def _post(self, body: dict) -> str:
        timeout = float(self.cfg.get("timeout", 1200))
        for _ in range(4):
            try:
                r = requests.post(self.url + "/api/chat", json=body, timeout=timeout)
            except requests.RequestException as e:
                raise ProviderError(f"ollama unreachable at {self.url}: {e}") from e
            if r.ok:
                return (r.json().get("message") or {}).get("content", "")
            err = r.text[:500]
            low = err.lower()
            if "think" in body and "think" in low:
                body.pop("think")  # model doesn't support the think flag
                continue
            if isinstance(body.get("format"), dict) and ("format" in low or "schema" in low or "grammar" in low):
                log.warning("ollama rejected the JSON schema, falling back to plain JSON mode")
                body["format"] = "json"
                continue
            if r.status_code == 404 or "not found" in low:
                raise ProviderError(f"model {body['model']} is not installed: run `ollama pull {body['model']}`")
            raise ProviderError(f"ollama HTTP {r.status_code}: {err}")
        raise ProviderError("ollama request failed after retries")
