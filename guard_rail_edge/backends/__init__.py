"""LLM backend abstractions for guard-rail-edge."""

from guard_rail_edge.backends.base import ChatBackend
from guard_rail_edge.backends.mock_backend import MockBackend
from guard_rail_edge.backends.ollama_backend import OllamaBackend
from guard_rail_edge.backends.openai_backend import OpenAIBackend


def get_backend(
    backend_type: str,
    model: str,
    base_url: str | None = None,
    host: str | None = None,
    timeout: float = 120.0,
    api_key_env: str = "OPENAI_API_KEY",
    mock: bool = False,
) -> ChatBackend:
    """Factory creating appropriate ChatBackend instance."""
    if mock:
        return MockBackend(model=model)

    b_type = (backend_type or "ollama").lower().strip()
    if b_type == "openai":
        url = base_url or host or "https://api.openai.com/v1"
        return OpenAIBackend(
            model=model,
            base_url=url,
            timeout=timeout,
            api_key_env=api_key_env,
        )
    elif b_type == "ollama":
        url = host or base_url or "http://localhost:11434"
        return OllamaBackend(
            model=model,
            host=url,
            timeout=timeout,
        )
    else:
        raise ValueError(
            f"Unsupported backend type '{backend_type}'. Supported backends: 'ollama', 'openai'."
        )


__all__ = [
    "ChatBackend",
    "OllamaBackend",
    "OpenAIBackend",
    "MockBackend",
    "get_backend",
]
