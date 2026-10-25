"""Base protocol and exceptions for LLM backends."""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ChatBackend(Protocol):
    """Protocol defining common interface for chat and completion backends."""

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

    def preflight(self, model: str) -> None:
        """Check that the model and backend service are reachable."""
        ...
