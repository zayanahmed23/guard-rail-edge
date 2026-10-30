"""Tests for configuration file loading, precedence order, init presets, and doctor command."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from guard_rail_edge.config import ConfigError, resolve_merged_config
from guard_rail_edge.main import app

runner = CliRunner(env={"COLUMNS": "200", "NO_COLOR": "1"})


def test_config_precedence_order(tmp_path: Path, monkeypatch):
    """Test precedence: built-in defaults < pyproject.toml < guard-rail-edge.toml < CLI flags."""
    monkeypatch.chdir(tmp_path)

    # 1. pyproject.toml alone
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[tool.guard-rail-edge]
model = "pyproject-model"
timeout = 42.0
""",
        encoding="utf-8",
    )

    cfg, path = resolve_merged_config()
    assert cfg["model"] == "pyproject-model"
    assert cfg["timeout"] == 42.0
    assert path == "pyproject.toml"

    # 2. guard-rail-edge.toml overrides pyproject.toml
    gre_toml = tmp_path / "guard-rail-edge.toml"
    gre_toml.write_text(
        """
model = "toml-model"
judge_model = "toml-judge"
""",
        encoding="utf-8",
    )

    cfg2, path2 = resolve_merged_config()
    assert cfg2["model"] == "toml-model"  # Overridden by guard-rail-edge.toml
    assert cfg2["timeout"] == 42.0  # Inherited from pyproject.toml
    assert cfg2["judge_model"] == "toml-judge"
    assert path2 == "guard-rail-edge.toml"

    # 3. CLI flag overrides both
    suite_file = tmp_path / "tests.json"
    suite_file.write_text(
        json.dumps({
            "system_prompt": "You are a safe bot.",
            "expected_output_format": "Text",
            "tests": [{"name": "t1", "input": "hello"}],
        }),
        encoding="utf-8",
    )

    res = runner.invoke(app, ["run", "--suite", str(suite_file), "--mock", "--model", "cli-model"])
    assert res.exit_code == 0, f"Failed with: {res.output}"
    assert "Config: guard-rail-edge.toml" in res.output
    assert "Target Model: cli-model" in res.output


def test_unknown_key_error(tmp_path: Path, monkeypatch):
    """Unknown keys in configuration files raise ConfigError and cause exit code 2."""
    monkeypatch.chdir(tmp_path)

    bad_toml = tmp_path / "guard-rail-edge.toml"
    bad_toml.write_text("unknown_option_abc = 12345\n", encoding="utf-8")

    with pytest.raises(ConfigError) as exc_info:
        resolve_merged_config()
    assert "Unknown configuration key 'unknown_option_abc'" in str(exc_info.value)

    # Test via CLI runner
    res = runner.invoke(app, ["run", "--config", str(bad_toml)])
    assert res.exit_code == 2
    assert "Unknown configuration key 'unknown_option_abc'" in res.output


def test_init_presets_write_valid_files(tmp_path: Path, monkeypatch):
    """init --preset for groq, ollama, and mock writes valid files that parse cleanly."""
    for preset_name in ("groq", "ollama", "mock"):
        p_dir = tmp_path / f"test_{preset_name}"
        p_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.chdir(p_dir)

        res = runner.invoke(app, ["init", "--preset", preset_name])
        assert res.exit_code == 0
        assert (p_dir / "tests.json").exists()
        assert (p_dir / "guard-rail-edge.toml").exists()

        # Check configuration parses without errors
        cfg, cfg_path = resolve_merged_config()
        assert cfg_path == "guard-rail-edge.toml"
        assert "on_review" in cfg
        assert cfg["on_review"] == "fail"

        if preset_name == "groq":
            assert cfg["target_backend"] == "groq"
            assert cfg["judge_backend"] == "groq"
            assert cfg["judge_model"] == "qwen/qwen3.8-27b"
            assert cfg["pack"] == ["all"]
        elif preset_name == "ollama":
            assert cfg["target_backend"] == "ollama"
            assert cfg["judge_backend"] == "ollama"
        elif preset_name == "mock":
            assert cfg["mock"] is True


def test_doctor_never_prints_env_var_values(tmp_path: Path, monkeypatch):
    """Critical security guarantee: doctor never prints secret API key values."""
    secret_groq = "sk-groq-CONFIDENTIAL-KEY-1122334455"
    secret_openai = "sk-openai-SUPER-SECRET-9988776655"
    monkeypatch.setenv("GROQ_API_KEY", secret_groq)
    monkeypatch.setenv("OPENAI_API_KEY", secret_openai)
    monkeypatch.chdir(tmp_path)

    res = runner.invoke(app, ["doctor"])
    output = res.output

    # Crucial security assertion: secrets must NEVER appear in output
    assert secret_groq not in output
    assert secret_openai not in output

    # Check status indicator appears
    assert "GROQ_API_KEY" in output
    assert "SET" in output


def test_doctor_exit_codes(tmp_path: Path, monkeypatch):
    """doctor exits 0 when environment is ready in mock mode, and exits 1 on blocking errors."""
    monkeypatch.chdir(tmp_path)

    # 1. Blocking error when config has invalid/unknown key
    bad_toml = tmp_path / "guard-rail-edge.toml"
    bad_toml.write_text("invalid_key_xyz = 999\n", encoding="utf-8")
    res_err = runner.invoke(app, ["doctor"])
    assert res_err.exit_code == 1
    assert "FAIL" in res_err.output

    # 2. Ready when mock mode and valid suite exist
    mock_toml = tmp_path / "guard-rail-edge.toml"
    suite_json = tmp_path / "tests.json"
    suite_json.write_text(
        json.dumps({
            "system_prompt": "You are a customer assistant.",
            "expected_output_format": "Text",
            "tests": [{"name": "t1", "input": "hi"}],
        }),
        encoding="utf-8",
    )
    mock_toml.write_text(
        """
suite = "tests.json"
mock = true
model = "mock-target"
judge_model = "mock-judge"
""",
        encoding="utf-8",
    )

    res_ok = runner.invoke(app, ["doctor"])
    assert res_ok.exit_code == 0
    assert "All pre-flight checks passed!" in res_ok.output
