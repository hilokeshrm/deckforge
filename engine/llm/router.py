"""Routes each task to a provider, validates JSON replies and falls back on failure."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError

from ..util import extract_json, log, strip_think
from .anthropic_provider import AnthropicProvider
from .base import LLMProvider, ProviderError
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAIProvider

T = TypeVar("T", bound=BaseModel)

TASKS = ("summarize", "plan", "edit", "vision", "caption", "brand", "review")
PROVIDERS = ("ollama", "openai", "anthropic")


class LLM:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.reload()

    def reload(self) -> None:
        lc = self.cfg.get("llm", {})
        self.providers: dict[str, LLMProvider] = {
            "ollama": OllamaProvider(lc.get("ollama", {})),
            "openai": OpenAIProvider(lc.get("openai", {})),
            "anthropic": AnthropicProvider(lc.get("anthropic", {})),
        }
        self.routing: dict = lc.get("routing", {})
        self.default: str = lc.get("default_provider", "ollama")
        self.fallback: list = lc.get("fallback_order", list(PROVIDERS))
        self.retries: int = int(lc.get("max_retries", 2))
        self._avail: dict[str, tuple[float, bool]] = {}

    def is_available(self, name: str) -> bool:
        cached = self._avail.get(name)
        if cached and time.time() - cached[0] < 60:
            return cached[1]
        ok = name in self.providers and self.providers[name].available()
        self._avail[name] = (time.time(), ok)
        return ok

    def order(self, task: str) -> list[str]:
        first = self.routing.get(task, self.default)
        names = [first] + [n for n in self.fallback if n != first]
        return [n for n in dict.fromkeys(names) if self.is_available(n)]

    def can(self, task: str) -> bool:
        return bool(self.order(task))

    def status(self) -> dict:
        out = {}
        for name, p in self.providers.items():
            ok = self.is_available(name)
            info = {"available": ok}
            if ok:
                try:
                    info.update(p.describe())
                except Exception as e:  # describe is best-effort
                    info["error"] = str(e)
            out[name] = info
        return out

    def text(self, task: str, system: str, prompt: str, images: list[Path] | None = None,
             max_tokens: int = 8000) -> str:
        errors = []
        for name in self.order(task):
            try:
                t0 = time.time()
                out = self.providers[name].complete(system, prompt, images, None, max_tokens)
                log.info("[%s] %s answered in %.1fs", task, name, time.time() - t0)
                return strip_think(out).strip()
            except ProviderError as e:
                log.warning("[%s] %s failed: %s", task, name, e)
                errors.append(f"{name}: {e}")
        raise ProviderError(f"no provider could handle '{task}': " + ("; ".join(errors) or "none available"))

    def structured(self, task: str, system: str, prompt: str, model_cls: Type[T],
                   images: list[Path] | None = None, max_tokens: int = 16000) -> T:
        schema = model_cls.model_json_schema()
        sys_prompt = (
            system
            + "\n\nRespond with ONLY one JSON object - no prose, no markdown fences - "
              "that validates against this JSON Schema:\n"
            + json.dumps(schema, separators=(",", ":"))
        )
        errors = []
        for name in self.order(task):
            provider = self.providers[name]
            p = prompt
            for attempt in range(self.retries + 1):
                try:
                    t0 = time.time()
                    raw = provider.complete(sys_prompt, p, images, schema, max_tokens)
                except ProviderError as e:
                    log.warning("[%s] %s failed: %s", task, name, e)
                    errors.append(f"{name}: {e}")
                    break
                try:
                    obj = model_cls.model_validate(extract_json(raw))
                    log.info("[%s] %s answered in %.1fs", task, name, time.time() - t0)
                    return obj
                except (ValueError, ValidationError) as e:
                    log.warning("[%s] %s gave invalid JSON (attempt %d): %s", task, name, attempt + 1, str(e)[:200])
                    errors.append(f"{name}: invalid JSON")
                    p = (prompt + "\n\nYOUR PREVIOUS REPLY WAS INVALID:\n" + str(e)[:1500]
                         + "\nReturn the complete, corrected JSON object only.")
        raise ProviderError(f"no provider produced valid output for '{task}': " + ("; ".join(errors) or "none available"))
