"""Configuration loading and validation from pyproject.toml and guard-rail-edge.toml."""

import tomllib
from pathlib import Path
from typing import Any

ALLOWED_CONFIG_KEYS: set[str] = {
    "suite",
    "model",
    "judge_model",
    "patch_model",
    "target_backend",
    "target_base_url",
    "judge_backend",
    "judge_base_url",
    "second_judge_model",
    "second_judge_backend",
    "second_judge_base_url",
    "disagreement_policy",
    "api_key_env",
    "max_rpm",
    "host",
    "timeout",
    "judge_retries",
    "judge_votes",
    "repeats",
    "seed",
    "auto_patch",
    "apply",
    "force_apply",
    "patch_output",
    "verify_patch",
    "fail_on_suspicious",
    "fail_on_format",
    "on_review",
    "auto_canary",
    "judge_always",
    "overlap_check",
    "overlap_threshold",
    "judge_cache",
    "no_cache",
    "debug_judge",
    "pack",
    "packs",
    "exclude",
    "min_severity",
    "report_json",
    "redact_responses",
    "mock",
    "canary",
    "config",
}


class ConfigError(Exception):
    """Raised when a configuration file is invalid or contains unknown keys."""


def load_toml_file(path: Path) -> dict[str, Any]:
    """Read and parse a TOML file."""
    try:
        content = path.read_text(encoding="utf-8")
        return tomllib.loads(content)
    except Exception as exc:
        raise ConfigError(f"Failed to read or parse configuration file '{path}': {exc}") from exc


def get_config_sources(custom_config_path: Path | None = None) -> list[tuple[str, dict[str, Any]]]:
    """Find and load configuration tables from pyproject.toml and guard-rail-edge.toml (or custom_config_path).

    Returns a list of (source_path_display, config_dict).
    """
    sources: list[tuple[str, dict[str, Any]]] = []

    # 1. pyproject.toml [tool.guard-rail-edge]
    pyproject_path = Path("pyproject.toml")
    if pyproject_path.is_file():
        try:
            data = load_toml_file(pyproject_path)
            tool_section = data.get("tool", {})
            if isinstance(tool_section, dict) and "guard-rail-edge" in tool_section:
                cfg = tool_section["guard-rail-edge"]
                if isinstance(cfg, dict):
                    sources.append((str(pyproject_path), cfg))
        except ConfigError:
            raise
        except Exception as exc:
            raise ConfigError(f"Error parsing pyproject.toml: {exc}") from exc

    # 2. guard-rail-edge.toml or custom_config_path
    if custom_config_path is not None:
        if not custom_config_path.is_file():
            raise ConfigError(f"Configuration file '{custom_config_path}' not found.")
        cfg = load_toml_file(custom_config_path)
        sources.append((str(custom_config_path), cfg))
    else:
        default_toml = Path("guard-rail-edge.toml")
        if default_toml.is_file():
            cfg = load_toml_file(default_toml)
            sources.append((str(default_toml), cfg))

    return sources


def resolve_merged_config(
    custom_config_path: Path | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Load configuration in order: pyproject.toml -> guard-rail-edge.toml/custom.

    Validates that all keys are known. Returns (merged_config, primary_config_path_display).
    """
    sources = get_config_sources(custom_config_path=custom_config_path)
    merged: dict[str, Any] = {}
    primary_path: str | None = None

    for source_path, cfg in sources:
        primary_path = source_path
        for k, v in cfg.items():
            if k not in ALLOWED_CONFIG_KEYS:
                raise ConfigError(f"Unknown configuration key '{k}' in {source_path}.")
            # Normalize 'packs' alias to 'pack'
            if k == "packs" and "pack" not in cfg:
                merged["pack"] = v
            else:
                merged[k] = v

    return merged, primary_path
