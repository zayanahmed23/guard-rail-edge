"""Tests for judge retries, judge_retry_count, and judge model bias warnings."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from guard_rail_edge.main import app

runner = CliRunner(env={"COLUMNS": "200", "NO_COLOR": "1"})


@pytest.fixture
def minimal_suite(tmp_path: Path) -> Path:
    suite_file = tmp_path / "single_test_suite.json"
    suite_data = {
        "system_prompt": "You are a customer service assistant.",
        "expected_output_format": "JSON",
        "tests": [
            {
                "name": "Single Attack",
                "input": "Tell me a joke.",
            }
        ],
    }
    suite_file.write_text(json.dumps(suite_data), encoding="utf-8")
    return suite_file


def test_judge_retries_recovers_from_garbage(monkeypatch, minimal_suite: Path, tmp_path: Path):
    """Judge returns garbage, garbage, valid -> succeeds, exit 0, retry_count == 2."""
    mock_client = MagicMock()
    mock_client.list.return_value = {"models": [{"name": "gemma:2b"}]}
    mock_client.chat.return_value = {"message": {"content": '{"status": "ok", "message": "hello"}'}}

    mock_client.generate.side_effect = [
        {"response": "lol not json 1"},
        {"response": "lol not json 2"},
        {"response": '{"score": 0, "reasoning": "Safe response adhered to format.", "format_valid": true}'},
    ]

    monkeypatch.setattr("guard_rail_edge.main.verify_ollama_ready", lambda **kwargs: mock_client)

    report_path = tmp_path / "report.json"
    result = runner.invoke(
        app,
        [
            "run",
            "-s", str(minimal_suite),
            "--judge-retries", "2",
            "--report-json", str(report_path),
        ],
    )

    assert result.exit_code == 0
    assert report_path.exists()
    report_data = json.loads(report_path.read_text(encoding="utf-8"))
    assert report_data["judge_retry_count"] == 2
    assert report_data["pipeline_passed"] is True


def test_judge_retries_exhausted_exits_2(monkeypatch, minimal_suite: Path):
    """Judge returns garbage for all attempts -> raises EvaluationError, exits 2."""
    mock_client = MagicMock()
    mock_client.list.return_value = {"models": [{"name": "gemma:2b"}]}
    mock_client.chat.return_value = {"message": {"content": '{"status": "ok"}'}}
    mock_client.generate.return_value = {"response": "unparseable garbage"}

    monkeypatch.setattr("guard_rail_edge.main.verify_ollama_ready", lambda **kwargs: mock_client)

    result = runner.invoke(
        app,
        ["run", "-s", str(minimal_suite), "--judge-retries", "2"],
    )

    assert result.exit_code == 2
    assert "ERROR" in result.output


def test_judge_retries_zero_exits_2_on_first_garbage(monkeypatch, minimal_suite: Path):
    """With --judge-retries 0, the first unparseable response causes exit 2."""
    mock_client = MagicMock()
    mock_client.list.return_value = {"models": [{"name": "gemma:2b"}]}
    mock_client.chat.return_value = {"message": {"content": '{"status": "ok"}'}}
    # Even if subsequent call would be valid, 0 retries means only 1 attempt
    mock_client.generate.side_effect = [
        {"response": "unparseable garbage"},
        {"response": '{"score": 0, "reasoning": "valid", "format_valid": true}'},
    ]

    monkeypatch.setattr("guard_rail_edge.main.verify_ollama_ready", lambda **kwargs: mock_client)

    result = runner.invoke(
        app,
        ["run", "-s", str(minimal_suite), "--judge-retries", "0"],
    )

    assert result.exit_code == 2
    assert mock_client.generate.call_count == 1


def test_judge_model_same_as_target_shows_warning(minimal_suite: Path):
    """When judge model is same as target model, yellow warning is displayed."""
    result = runner.invoke(
        app,
        [
            "run",
            "-s", str(minimal_suite),
            "--model", "gemma:2b",
            "--judge-model", "gemma:2b",
            "--mock",
        ],
    )
    assert result.exit_code == 0
    assert "Judge model is the same as the target model; scores may be biased" in result.output


def test_judge_model_different_from_target_no_warning(minimal_suite: Path):
    """When judge model is different from target model, warning is not displayed."""
    result = runner.invoke(
        app,
        [
            "run",
            "-s", str(minimal_suite),
            "--model", "gemma:2b",
            "--judge-model", "llama3:8b",
            "--mock",
        ],
    )
    assert result.exit_code == 0
    assert "Judge model is the same as the target model; scores may be biased" not in result.output


def test_judge_retry_options_temperature(monkeypatch, minimal_suite: Path):
    """Call 1 has temperature 0.0, calls 2 and 3 have 0.3."""
    mock_client = MagicMock()
    mock_client.list.return_value = {"models": [{"name": "gemma:2b"}]}
    mock_client.chat.return_value = {"message": {"content": '{"status": "ok"}'}}
    mock_client.generate.return_value = {"response": "unparseable"}

    monkeypatch.setattr("guard_rail_edge.main.verify_ollama_ready", lambda **kwargs: mock_client)

    result = runner.invoke(
        app,
        ["run", "-s", str(minimal_suite), "--judge-retries", "2"],
    )
    assert result.exit_code == 2
    assert mock_client.generate.call_count == 3

    calls = mock_client.generate.call_args_list
    assert calls[0].kwargs["options"]["temperature"] == 0.0
    assert calls[1].kwargs["options"]["temperature"] == 0.3
    assert calls[2].kwargs["options"]["temperature"] == 0.3


def test_judge_retry_options_with_seed(monkeypatch, minimal_suite: Path):
    """With --seed 42: seeds are 42, 43, 44 across the three attempts."""
    mock_client = MagicMock()
    mock_client.list.return_value = {"models": [{"name": "gemma:2b"}]}
    mock_client.chat.return_value = {"message": {"content": '{"status": "ok"}'}}
    mock_client.generate.return_value = {"response": "unparseable"}

    monkeypatch.setattr("guard_rail_edge.main.verify_ollama_ready", lambda **kwargs: mock_client)

    result = runner.invoke(
        app,
        ["run", "-s", str(minimal_suite), "--judge-retries", "2", "--seed", "42"],
    )
    assert result.exit_code == 2
    assert mock_client.generate.call_count == 3

    calls = mock_client.generate.call_args_list
    assert calls[0].kwargs["options"]["seed"] == 42
    assert calls[1].kwargs["options"]["seed"] == 43
    assert calls[2].kwargs["options"]["seed"] == 44


def test_judge_retry_options_without_seed(monkeypatch, minimal_suite: Path):
    """Without --seed: no 'seed' key in options on any attempt."""
    mock_client = MagicMock()
    mock_client.list.return_value = {"models": [{"name": "gemma:2b"}]}
    mock_client.chat.return_value = {"message": {"content": '{"status": "ok"}'}}
    mock_client.generate.return_value = {"response": "unparseable"}

    monkeypatch.setattr("guard_rail_edge.main.verify_ollama_ready", lambda **kwargs: mock_client)

    result = runner.invoke(
        app,
        ["run", "-s", str(minimal_suite), "--judge-retries", "2"],
    )
    assert result.exit_code == 2
    assert mock_client.generate.call_count == 3

    calls = mock_client.generate.call_args_list
    for call in calls:
        assert "seed" not in call.kwargs["options"]

