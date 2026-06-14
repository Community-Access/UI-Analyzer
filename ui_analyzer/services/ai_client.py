"""Base interface for all AI providers."""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Generator

class AIClient(ABC):
    """Abstract base class for AI LLM clients."""

    @abstractmethod
    def stream_chat(
        self,
        model: str,
        messages: list[dict],
    ) -> Generator[str, None, None]:
        """Stream assistant content tokens. Yields incremental strings."""
        ...

    @abstractmethod
    def respond(self, model: str, messages: list[dict]) -> str:
        """Collect and return the full response."""
        ...

    @abstractmethod
    def list_models(self) -> list[dict]:
        """Return a list of available models with metadata."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is reachable and configured."""
        ...
