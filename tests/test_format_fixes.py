"""Tests for Task 10 format checks and small correctness fixes."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from guard_rail_edge.evaluator import (
    EvaluatorConnectionError,
    check_format,
    verify_ollama_ready,
)
from guard_rail_edge.main import app

runner = CliRunner(env={"COLUMNS": "200", "NO_COLOR": "1"})


def test_check_format_required_json_keys() -> None:
    """When required_json_keys are set, check_format verifies parsed object is a dict containing all keys."""
    valid_json = json.dumps({"status": "ok", "message": "done", "extra": 123})
    assert check_format(valid_json, "JSON", required_json_keys=["status", "message"]) is True

    # Missing a required key
    missing_key = json.dumps({"status": "ok"})
    assert check_format(missing_key, "JSON", required_json_keys=["status", "message"]) is False

    # Valid JSON, but not a dict (e.g. a list)
    list_json = json.dumps(["status", "message"])
    assert check_format(list_json, "JSON", required_json_keys=["status"]) is False


def test_check_format_fenced_block_with_language_tag() -> None:
    """check_format for JSON should accept fenced blocks with ```json tag."""
    fenced = "```json\n{\"status\": \"ok\", \"count\": 42}\n```"
    assert check_format(fenced, "JSON") is True
    assert check_format(fenced, "JSON", required_json_keys=["status"]) is True

    # With surrounding text
    surrounded = "Here is your requested output:\n```json\n{\"status\": \"success\"}\n```\nHope that helps!"
    assert check_format(surrounded, "JSON", required_json_keys=["status"]) is True


def test_verify_ollama_ready_no_partial_prefix_matching(monkeypatch) -> None:
    """verify_ollama_ready: 'gemma' must NOT match 'gemma:7b', only 'gemma' or 'gemma:latest'."""
    mock_client = MagicMock()
    # Ollama library only has gemma:7b
    mock_client.list.return_value = {"models": [{"name": "gemma:7b"}]}
    monkeypatch.setattr("guard_rail_edge.evaluator.ollama.Client", lambda *args, **kwargs: mock_client)

    # Looking for "gemma" should fail because only "gemma:7b" exists
    with pytest.raises(EvaluatorConnectionError) as exc_info:
        verify_ollama_ready("gemma")
    assert "Model 'gemma' is not pulled" in str(exc_info.value)

    # Looking for "gemma:7b" specifically should succeed
    ready_client = verify_ollama_ready("gemma:7b")
    assert ready_client == mock_client

    # Ollama library having gemma:latest matches "gemma"
    mock_client.list.return_value = {"models": [{"name": "gemma:latest"}]}
    assert verify_ollama_ready("gemma") == mock_client


def test_redact_responses_flag(tmp_path: Path) -> None:
    """--redact-responses flag replaces target_response in report with first 80 chars + '...[redacted]'."""
    suite_file = tmp_path / "suite.json"
    long_secret = "SECRET_" + "A" * 150
    suite_file.write_text(
        json.dumps({
            "system_prompt": "You are a customer service bot.",
            "expected_output_format": "JSON",
            "tests": [{"name": "Test leak", "input": long_secret}],
        }),
        encoding="utf-8",
    )
    report_unredacted = tmp_path / "report_unredacted.json"
    report_redacted = tmp_path / "report_redacted.json"

    # Run without redact flag
    res1 = runner.invoke(
        app,
        [
            "run",
            "--suite", str(suite_file),
            "--mock",
            "--report-json", str(report_unredacted),
        ],
    )
    assert res1.exit_code == 0
    data1 = json.loads(report_unredacted.read_text(encoding="utf-8"))
    assert "...[redacted]" not in data1["results"][0]["target_response"]

    # Run with --redact-responses flag
    res2 = runner.invoke(
        app,
        [
            "run",
            "--suite", str(suite_file),
            "--mock",
            "--redact-responses",
            "--report-json", str(report_redacted),
        ],
    )
    assert res2.exit_code == 0
    data2 = json.loads(report_redacted.read_text(encoding="utf-8"))
    resp_text = data2["results"][0]["target_response"]
    assert resp_text.endswith("...[redacted]")
    # First part is up to 80 chars
    prefix = resp_text[:-len("...[redacted]")]
    assert len(prefix) <= 80
