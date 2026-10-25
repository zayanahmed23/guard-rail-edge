"""Unit tests for judge self-consistency voting and aggregation."""

import json
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from guard_rail_edge.evaluator import EvaluationError, grade_interaction
from guard_rail_edge.main import app


def test_grade_interaction_votes_majority():
    """Test that majority score is selected when judge votes disagree."""
    client = MagicMock()
    # 3 responses: score 0, score 1, score 0 -> majority is 0
    client.generate.side_effect = [
        {"response": json.dumps({"score": 0, "reasoning": "First vote safe", "format_valid": True})},
        {"response": json.dumps({"score": 1, "reasoning": "Second vote suspicious", "format_valid": True})},
        {"response": json.dumps({"score": 0, "reasoning": "Third vote safe", "format_valid": True})},
    ]

    verdict = grade_interaction(
        client=client,
        model_name="test-judge",
        system_prompt="You are a safe bot.",
        expected_output_format="Text",
        adversarial_input="Hello",
        target_response="Hello world",
        programmatic_format_ok=True,
        judge_votes=3,
        seed=42,
    )

    assert verdict.score == 0
    assert verdict.votes == [0, 1, 0]
    assert "Majority vote 0" in verdict.reasoning
    assert client.generate.call_count == 3


def test_grade_interaction_votes_tie_takes_max():
    """Test that a tie between scores picks max(tied_scores) for security conservatism."""
    client = MagicMock()
    # 2 responses: score 1 and score 2 -> tie between 1 and 2 -> max is 2
    client.generate.side_effect = [
        {"response": json.dumps({"score": 1, "reasoning": "Vote suspicious", "format_valid": True})},
        {"response": json.dumps({"score": 2, "reasoning": "Vote jailbroken", "format_valid": True})},
    ]

    verdict = grade_interaction(
        client=client,
        model_name="test-judge",
        system_prompt="You are a safe bot.",
        expected_output_format="Text",
        adversarial_input="Attack",
        target_response="Jailbreak text",
        programmatic_format_ok=True,
        judge_votes=2,
    )

    assert verdict.score == 2
    assert verdict.votes == [1, 2]
    assert "Majority vote 2" in verdict.reasoning


def test_grade_interaction_votes_handles_single_failure():
    """Test that voting can proceed if one vote attempt fails after retries but others succeed."""
    client = MagicMock()
    # Vote 1 fails all retries (e.g. judge_retries=0 so 1 attempt)
    # Vote 2 succeeds with score 1
    # Vote 3 succeeds with score 1
    client.generate.side_effect = [
        Exception("Transient network issue"),
        {"response": json.dumps({"score": 1, "reasoning": "Vote suspicious", "format_valid": True})},
        {"response": json.dumps({"score": 1, "reasoning": "Vote suspicious", "format_valid": True})},
    ]

    verdict = grade_interaction(
        client=client,
        model_name="test-judge",
        system_prompt="You are a safe bot.",
        expected_output_format="Text",
        adversarial_input="Attack",
        target_response="Response",
        programmatic_format_ok=True,
        judge_votes=3,
        judge_retries=0,
    )

    assert verdict.score == 1
    assert verdict.votes == [1, 1]


def test_grade_interaction_votes_all_fail_raises():
    """Test that if all votes fail, EvaluationError is raised."""
    client = MagicMock()
    client.generate.side_effect = Exception("Fatal backend crash")

    with pytest.raises(EvaluationError, match="Evaluator execution failed"):
        grade_interaction(
            client=client,
            model_name="test-judge",
            system_prompt="System",
            expected_output_format="Text",
            adversarial_input="Attack",
            target_response="Resp",
            programmatic_format_ok=True,
            judge_votes=2,
            judge_retries=0,
        )


def test_grade_interaction_mock_with_votes():
    """Test mock mode with judge_votes > 1 populates votes list."""
    verdict = grade_interaction(
        client=None,
        model_name="mock-model",
        system_prompt="System",
        expected_output_format="Text",
        adversarial_input="Attack",
        target_response="I cannot comply with this request.",
        programmatic_format_ok=True,
        mock_mode=True,
        judge_votes=3,
    )

    assert verdict.score == 0
    assert verdict.votes == [0, 0, 0]


def test_cli_run_with_judge_votes(tmp_path):
    """Test running CLI with --judge-votes flag in mock mode."""
    suite_file = tmp_path / "suite.json"
    suite_file.write_text(
        json.dumps({
            "system_prompt": "You are a customer service assistant.",
            "expected_output_format": "JSON",
            "tests": [
                {"name": "Test 1", "input": "Hello"}
            ]
        }),
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(app, [
        "run",
        "--suite", str(suite_file),
        "--mock",
        "--judge-votes", "3",
    ])
    assert result.exit_code == 0


def test_cli_calibrate_with_judge_votes():
    """Test running calibrate CLI with --judge-votes flag in mock mode."""
    runner = CliRunner()
    result = runner.invoke(app, [
        "calibrate",
        "--mock",
        "--judge-votes", "2",
    ])
    assert result.exit_code == 0
    assert "TRUSTWORTHY" in result.output
    assert "Confusion Matrix" in result.output
