"""Ollama backend wrapping the official ollama Python client."""

import os
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
        self.client = client

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        seed: int | None = None,
        json_schema: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> str:
        client = self.client or ollama.Client(host=self.host, timeout=self.timeout)
        options: dict[str, Any] = {"temperature": temperature}
        num_threads = os.environ.get("OLLAMA_NUM_THREADS")
        if num_threads:
            try:
                options["num_thread"] = int(num_threads)
            except ValueError:
                pass
        if seed is not None:
            options["seed"] = seed

        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "options": options,
        }
        if json_schema is not None:
            kwargs["format"] = json_schema

        response = client.chat(**kwargs)
        if isinstance(response, dict):
            content_val = response.get("message", {}).get("content", "")
            if isinstance(content_val, dict):
                import json

                return json.dumps(content_val)
            return str(content_val).strip()
        if hasattr(response, "message"):
            msg = response.message
            if hasattr(msg, "content"):
                return str(msg.content).strip()
            if isinstance(msg, dict):
                return str(msg.get("content", "")).strip()
        return str(response).strip()

    def generate(
        self,
        prompt: str,
        temperature: float = 0.0,
        seed: int | None = None,
        json_schema: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> str:
        client = self.client or ollama.Client(host=self.host, timeout=self.timeout)
        options: dict[str, Any] = {"temperature": temperature}
        num_threads = os.environ.get("OLLAMA_NUM_THREADS")
        if num_threads:
            try:
                options["num_thread"] = int(num_threads)
            except ValueError:
                pass
        if seed is not None:
            options["seed"] = seed

        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "prompt": prompt,
            "options": options,
        }
        if json_schema is not None:
            kwargs["format"] = json_schema

        response = client.generate(**kwargs)
        if isinstance(response, dict):
            raw_val = response.get("response", "")
            if isinstance(raw_val, dict):
                import json

                return json.dumps(raw_val)
            return str(raw_val).strip()
        if hasattr(response, "response"):
            return str(response.response).strip()
        return str(response).strip()

    def preflight(self, model: str) -> None:
        import sys

        main_mod = sys.modules.get("guard_rail_edge.main")
        verify_fn = getattr(main_mod, "verify_ollama_ready", verify_ollama_ready)
        ready_client = verify_fn(host=self.host, model_name=model, timeout=self.timeout)
        if ready_client is not None:
            self.client = ready_client
