"""Tests for --repeats and --seed in guard_rail_edge."""

import json
from pathlib import Path
from unittest.mock import MagicMock

from typer.testing import CliRunner

from guard_rail_edge.main import app

runner = CliRunner(env={"COLUMNS": "200", "NO_COLOR": "1"})


def test_repeats_max_score_and_run_scores_stored(tmp_path: Path, monkeypatch) -> None:
    """Mocked judge returning [0, 2, 0] across 3 repeats -> final score 2, exit 1, report stores run_scores."""
    suite_file = tmp_path / "suite.json"
    suite_file.write_text(
        json.dumps({
            "system_prompt": "You are a helpful assistant.",
            "expected_output_format": "JSON",
            "tests": [{"name": "flaky_test", "input": "test prompt"}],
        }),
        encoding="utf-8",
    )
    report_file = tmp_path / "report.json"

    # Mock ollama.Client
    mock_client = MagicMock()
    mock_client.list.return_value = {"models": [{"name": "gemma:2b"}]}
    mock_client.chat.return_value = {
        "message": {"content": json.dumps({"status": "ok"})}
    }

    # Simulate scores [0, 2, 0] across 3 repeats
    scores = [
        {"score": 0, "reasoning": "First run safe", "format_valid": True},
        {"score": 2, "reasoning": "Second run jailbroken", "format_valid": True},
        {"score": 0, "reasoning": "Third run safe", "format_valid": True},
    ]
    call_idx = 0

    def mock_generate(*args, **kwargs):
        nonlocal call_idx
        idx = min(call_idx, len(scores) - 1)
        resp = scores[idx]
        call_idx += 1
        return {"response": json.dumps(resp)}

    mock_client.generate.side_effect = mock_generate

    monkeypatch.setattr("guard_rail_edge.evaluator.ollama.Client", lambda *args, **kwargs: mock_client)

    result = runner.invoke(
        app,
        [
            "run",
            "--suite", str(suite_file),
            "--repeats", "3",
            "--report-json", str(report_file),
        ],
    )

    assert result.exit_code == 1
    assert report_file.exists()
    report_data = json.loads(report_file.read_text(encoding="utf-8"))
    assert len(report_data["results"]) == 1
    res = report_data["results"][0]
    assert res["score"] == 2
    assert res["run_scores"] == [0, 2, 0]
    assert "Second run jailbroken" in res["reasoning"]


def test_seed_passed_to_ollama_options(tmp_path: Path, monkeypatch) -> None:
    """Assert seed is passed to client.chat and client.generate options."""
    suite_file = tmp_path / "suite.json"
    suite_file.write_text(
        json.dumps({
            "system_prompt": "You are a helpful assistant.",
            "expected_output_format": "JSON",
            "tests": [{"name": "seeded_test", "input": "test input"}],
        }),
        encoding="utf-8",
    )

    mock_client = MagicMock()
    mock_client.list.return_value = {"models": [{"name": "gemma:2b"}]}
    mock_client.chat.return_value = {
        "message": {"content": json.dumps({"status": "ok"})}
    }
    mock_client.generate.return_value = {
        "response": json.dumps({"score": 0, "reasoning": "Safe", "format_valid": True})
    }

    monkeypatch.setattr("guard_rail_edge.evaluator.ollama.Client", lambda *args, **kwargs: mock_client)

    result = runner.invoke(
        app,
        [
            "run",
            "--suite", str(suite_file),
            "--seed", "12345",
        ],
    )

    assert result.exit_code == 0
    # Check that chat received seed=12345 in options
    chat_kwargs = mock_client.chat.call_args.kwargs
    assert "options" in chat_kwargs
    assert chat_kwargs["options"].get("seed") == 12345

    # Check that generate received seed=12345 in options
    gen_kwargs = mock_client.generate.call_args.kwargs
    assert "options" in gen_kwargs
    assert gen_kwargs["options"].get("seed") == 12345
