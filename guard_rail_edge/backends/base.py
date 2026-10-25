"""Base interface for LLM backends."""

from abc import ABC, abstractmethod
from typing import Any


class ChatBackend(ABC):
    """Abstract base class defining common interface for chat and completion backends."""

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        seed: int | None = None,
        json_schema: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> str:
        """Send chat messages and return the assistant reply text."""
        ...

    @abstractmethod
    def generate(
        self,
        prompt: str,
        temperature: float = 0.0,
        seed: int | None = None,
        json_schema: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> str:
        """Send a prompt and return the completion text."""
        ...

    @abstractmethod
    def preflight(self, model: str) -> None:
        """Check that the model and backend service are reachable."""
        ...

