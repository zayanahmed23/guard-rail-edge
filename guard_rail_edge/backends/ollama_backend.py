"""Ollama backend wrapping the official ollama Python client."""

from typing import Any

import ollama

from guard_rail_edge.backends.base import ChatBackend
from guard_rail_edge.evaluator import verify_ollama_ready


class OllamaBackend(ChatBackend):
    """Chat backend using local Ollama daemon."""

    def __init__(
        self,
        model: str,
        host: str = "http://localhost:11434",
        timeout: float = 120.0,
        client: ollama.Client | None = None,
    ) -> None:
        self.model = model
        self.host = host
        self.timeout = timeout
        self.client = client or ollama.Client(host=host, timeout=timeout)

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        seed: int | None = None,
        json_schema: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> str:
        options: dict[str, Any] = {"temperature": temperature}
        if seed is not None:
            options["seed"] = seed

        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "options": options,
        }
        if json_schema is not None:
            kwargs["format"] = json_schema

        response = self.client.chat(**kwargs)
        return str(response.get("message", {}).get("content", "")).strip()

    def generate(
        self,
        prompt: str,
        temperature: float = 0.0,
        seed: int | None = None,
        json_schema: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> str:
        options: dict[str, Any] = {"temperature": temperature}
        if seed is not None:
            options["seed"] = seed

        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "prompt": prompt,
            "options": options,
        }
        if json_schema is not None:
            kwargs["format"] = json_schema

        response = self.client.generate(**kwargs)
        return str(response.get("response", "")).strip()

    def preflight(self, model: str) -> None:
        verify_ollama_ready(host=self.host, model_name=model, timeout=self.timeout)
