"""Provider presets for free and popular hosted OpenAI-compatible inference APIs."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderPreset:
    name: str
    base_url: str
    api_key_env: str
    default_max_rpm: int
    description: str


PROVIDER_PRESETS: dict[str, ProviderPreset] = {
    "groq": ProviderPreset(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        default_max_rpm=25,
        description="Groq high-speed LPUs (free tier)",
    ),
    "openrouter": ProviderPreset(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        default_max_rpm=15,
        description="OpenRouter unified API gateway (free tier available)",
    ),
    "gemini": ProviderPreset(
        name="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key_env="GEMINI_API_KEY",
        default_max_rpm=10,
        description="Google Gemini OpenAI-compatible endpoint",
    ),
    "github": ProviderPreset(
        name="github",
        base_url="https://models.github.ai/inference",
        api_key_env="GITHUB_MODELS_TOKEN",
        default_max_rpm=10,
        description="GitHub Models marketplace inference endpoint",
    ),
}


def get_preset(name: str | None) -> ProviderPreset | None:
    """Lookup a provider preset by case-insensitive name."""
    if not name:
        return None
    return PROVIDER_PRESETS.get(name.lower().strip())
