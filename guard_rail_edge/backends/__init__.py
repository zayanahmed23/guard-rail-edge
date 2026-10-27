"""LLM backend abstractions for guard-rail-edge."""

from guard_rail_edge.backends.base import ChatBackend
from guard_rail_edge.backends.mock_backend import MockBackend
from guard_rail_edge.backends.ollama_backend import OllamaBackend
from guard_rail_edge.backends.openai_backend import OpenAIBackend
from guard_rail_edge.backends.presets import get_preset


def get_backend(
    backend_type: str,
    model: str,
    base_url: str | None = None,
    host: str | None = None,
    timeout: float = 120.0,
    api_key_env: str = "OPENAI_API_KEY",
    mock: bool = False,
    oracle_scores: dict[str, int] | None = None,
    max_rpm: int | None = None,
) -> ChatBackend:
    """Factory creating appropriate ChatBackend instance."""
    if mock:
        return MockBackend(model=model, oracle_scores=oracle_scores)

    b_type = (backend_type or "ollama").lower().strip()
    preset = get_preset(b_type)
    if preset is not None:
        url = base_url or host or preset.base_url
        key_env = api_key_env if api_key_env != "OPENAI_API_KEY" else preset.api_key_env
        rpm = max_rpm if max_rpm is not None else preset.default_max_rpm
        return OpenAIBackend(
            model=model,
            base_url=url,
            timeout=timeout,
            api_key_env=key_env,
            max_rpm=rpm,
            backend_type=b_type,
        )
    elif b_type == "openai":
        url = base_url or host or "https://api.openai.com/v1"
        return OpenAIBackend(
            model=model,
            base_url=url,
            timeout=timeout,
            api_key_env=api_key_env,
            max_rpm=max_rpm,
            backend_type="openai",
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
            f"Unsupported backend type '{backend_type}'. Supported backends: 'ollama', 'openai', 'groq', 'openrouter', 'gemini', 'github'."
        )


__all__ = [
    "ChatBackend",
    "OllamaBackend",
    "OpenAIBackend",
    "MockBackend",
    "get_backend",
    "get_preset",
]
