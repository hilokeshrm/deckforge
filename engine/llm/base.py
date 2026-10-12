from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class ProviderError(RuntimeError):
    """The provider failed in a way that retrying the same provider won't fix."""


class LLMProvider(ABC):
    name = "base"

    def __init__(self, cfg: dict):
        self.cfg = cfg or {}

    @abstractmethod
    def available(self) -> bool:
        """Cheap check: configured (key present / server reachable)."""

    @abstractmethod
    def complete(
        self,
        system: str,
        prompt: str,
        images: list[Path] | None = None,
        json_schema: dict | None = None,
        max_tokens: int = 16000,
    ) -> str:
        """Return the model's text reply. Raise ProviderError on failure."""

    def describe(self) -> dict:
        return {"name": self.name}
