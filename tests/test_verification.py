"""Tests for Task 6: Meaningful verification loop, safe --apply gating, and render_hardened_suite."""

import json
from pathlib import Path
from unittest.mock import MagicMock

from typer.testing import CliRunner

from guard_rail_edge import __version__
from guard_rail_edge.main import app
from guard_rail_edge.patcher import (
    generate_hardened_prompt,
    render_hardened_suite,
)
from guard_rail_edge.schemas import (
    EvaluationScore,
    HardenedPromptProposal,
    TestResult,
)

runner = CliRunner(env={"COLUMNS": "200", "NO_COLOR": "1"})


# ==============================================================================
# render_hardened_suite UNIT TESTS
# ==============================================================================


def test_render_hardened_suite_preserves_2_space_and_crlf():
    orig = '{\r\n  "system_prompt": "Original prompt.",\r\n  "expected_output_format": "JSON",\r\n  "tests": []\r\n}\r\n'
    hardened = "Hardened prompt with 🛡️ and rules."
    rendered = render_hardened_suite(orig, hardened)

    assert "\r\n" in rendered
    assert '  "system_prompt": "Hardened prompt with 🛡️ and rules."' in rendered
    assert rendered.endswith("\r\n")

    # Round-trip verification
    data = json.loads(rendered)
    assert data["system_prompt"] == hardened
    assert data["expected_output_format"] == "JSON"


def test_render_hardened_suite_preserves_4_space_and_lf():
    orig = '{\n    "system_prompt": "Original 4-space prompt.",\n    "expected_output_format": "JSON",\n    "tests": []\n}\n'
    hardened = "Hardened 4-space prompt."
    rendered = render_hardened_suite(orig, hardened)

    assert "\r\n" not in rendered
    assert rendered.endswith("\n")
    assert '    "system_prompt": "Hardened 4-space prompt."' in rendered

    data = json.loads(rendered)
    assert data["system_prompt"] == hardened


def test_render_hardened_suite_preserves_tabs():
    orig = '{\n\t"system_prompt": "Original tab prompt.",\n\t"expected_output_format": "JSON",\n\t"tests": []\n}'
    hardened = "Hardened tab prompt."
    rendered = render_hardened_suite(orig, hardened)

    assert '	"system_prompt": "Hardened tab prompt."' in rendered
    # Original did not have trailing newline
    assert not rendered.endswith("\n")

    data = json.loads(rendered)
    assert data["system_prompt"] == hardened


def test_render_hardened_suite_escapes_quotes_backslashes_newlines():
    orig = '{\n  "system_prompt": "Original prompt.",\n  "expected_output_format": "JSON",\n  "tests": []\n}\n'
    complex_prompt = (
        'Rule 1: "Never" say "yes".\n'
        'Rule 2: Path is C:\\Users\\Admin\\Secret.\n'
        'Rule 3: Unicode 🚀 and special chars: \t \r'
    )
    rendered = render_hardened_suite(orig, complex_prompt)

    # Must be strictly valid JSON
    data = json.loads(rendered)
    assert data["system_prompt"] == complex_prompt


# ==============================================================================
# VERIFICATION & SAFE APPLY TESTS
# ==============================================================================


def test_verification_regressed_blocks_apply(tmp_path: Path, monkeypatch):
    """When hardened prompt fixes test A but breaks previously-safe test B -> REGRESSED, --apply does NOT modify file."""
    suite_file = tmp_path / "tests.json"
    initial_content = json.dumps({
        "system_prompt": "Original system prompt.",
        "expected_output_format": "JSON",
        "tests": [
            {"name": "Test A", "input": "Attack A"},
            {"name": "Test B", "input": "Attack B"},
        ],
    }, indent=2) + "\n"
    suite_file.write_text(initial_content, encoding="utf-8")

    mock_client = MagicMock()
    monkeypatch.setattr("guard_rail_edge.main.verify_ollama_ready", lambda **kwargs: mock_client)

    # Simulation responses:
    # Initial run: Test A returns breached, Test B returns safe
    # Hardened run: Test A returns safe, Test B returns breached (regression!)
    call_counts = {"sim": 0, "judge": 0}

    def fake_sim(client, model_name, system_prompt, adversarial_input, mock_mode=False):
        call_counts["sim"] += 1
        if "Attack A" in adversarial_input:
            if "HARDENED" in system_prompt:
                return "Attack A resisted safely"
            return "Attack A breached raw prompt"
        if "Attack B" in adversarial_input:
            if "HARDENED" in system_prompt:
                return "Attack B regressed and breached"
            return "Attack B safe"
        return "Safe"

    def fake_judge(client, model_name, system_prompt, expected_output_format, adversarial_input, target_response, programmatic_format_ok, mock_mode=False, canary=None):
        if "breached" in target_response:
            return EvaluationScore(score=2, reasoning="Jailbroken response", format_valid=True)
        return EvaluationScore(score=0, reasoning="Safe response", format_valid=True)

    monkeypatch.setattr("guard_rail_edge.main.run_target_simulation", fake_sim)
    monkeypatch.setattr("guard_rail_edge.main.grade_interaction", fake_judge)

    # Patch proposal returns a hardened prompt with "HARDENED"
    monkeypatch.setattr(
        "guard_rail_edge.main.generate_hardened_prompt",
        lambda **kwargs: (
            HardenedPromptProposal(
                hardened_system_prompt="HARDENED system prompt.",
                security_improvements=["Defense added"],
            ),
            "llm",
        ),
    )

    result = runner.invoke(
        app,
        ["run", "--suite", str(suite_file), "--apply"],
    )

    # Should report REGRESSED in the table
    assert "[REGRESSED]" in result.output
    # Red warning message
    assert "Hardened prompt did not pass verification; suite file NOT modified" in result.output
    # Suite file must remain UNTOUCHED
    assert suite_file.read_text(encoding="utf-8") == initial_content
    # Exit code reflects original failure (1)
    assert result.exit_code == 1


def test_verification_fixes_all_allows_apply(tmp_path: Path, monkeypatch):
    """When hardened prompt fixes everything -> --apply writes file, exit 0."""
    suite_file = tmp_path / "tests.json"
    initial_content = json.dumps({
        "system_prompt": "Original system prompt.",
        "expected_output_format": "JSON",
        "tests": [
            {"name": "Test A", "input": "Attack A"},
        ],
    }, indent=2) + "\n"
    suite_file.write_text(initial_content, encoding="utf-8")

    mock_client = MagicMock()
    monkeypatch.setattr("guard_rail_edge.main.verify_ollama_ready", lambda **kwargs: mock_client)

    def fake_sim(client, model_name, system_prompt, adversarial_input, mock_mode=False):
        if "HARDENED" in system_prompt:
            return "Safe hardened output"
        return "Breached original output"

    def fake_judge(client, model_name, system_prompt, expected_output_format, adversarial_input, target_response, programmatic_format_ok, mock_mode=False, canary=None):
        if "Breached" in target_response:
            return EvaluationScore(score=2, reasoning="Jailbreak detected", format_valid=True)
        return EvaluationScore(score=0, reasoning="Safe response", format_valid=True)

    monkeypatch.setattr("guard_rail_edge.main.run_target_simulation", fake_sim)
    monkeypatch.setattr("guard_rail_edge.main.grade_interaction", fake_judge)

    hardened_text = "HARDENED system prompt."
    monkeypatch.setattr(
        "guard_rail_edge.main.generate_hardened_prompt",
        lambda **kwargs: (
            HardenedPromptProposal(
                hardened_system_prompt=hardened_text,
                security_improvements=["Boundary enforced"],
            ),
            "llm",
        ),
    )

    result = runner.invoke(
        app,
        ["run", "--suite", str(suite_file), "--apply"],
    )

    assert result.exit_code == 0
    assert "[FIXED]" in result.output
    assert "Applied hardened system prompt directly to suite file" in result.output

    # Content on disk matches render_hardened_suite
    expected_content = render_hardened_suite(initial_content, hardened_text)
    assert suite_file.read_text(encoding="utf-8") == expected_content


def test_apply_no_verify_patch_requires_force_apply(tmp_path: Path):
    """--apply with --no-verify-patch without --force-apply -> exit 2, file untouched."""
    suite_file = tmp_path / "tests.json"
    initial_content = json.dumps({
        "system_prompt": "Original prompt.",
        "expected_output_format": "JSON",
        "tests": [{"name": "A", "input": "override"}],
    }, indent=2) + "\n"
    suite_file.write_text(initial_content, encoding="utf-8")

    result = runner.invoke(
        app,
        ["run", "--suite", str(suite_file), "--mock", "--apply", "--no-verify-patch"],
    )

    assert result.exit_code == 2
    assert "--apply with --no-verify-patch requires --force-apply" in result.output
    # Suite file untouched
    assert suite_file.read_text(encoding="utf-8") == initial_content


def test_apply_no_verify_patch_with_force_apply(tmp_path: Path):
    """--apply with --no-verify-patch WITH --force-apply modifies the file."""
    suite_file = tmp_path / "tests.json"
    initial_content = json.dumps({
        "system_prompt": "Original prompt.",
        "expected_output_format": "JSON",
        "tests": [{"name": "A", "input": "override"}],
    }, indent=2) + "\n"
    suite_file.write_text(initial_content, encoding="utf-8")

    result = runner.invoke(
        app,
        ["run", "--suite", str(suite_file), "--mock", "--apply", "--no-verify-patch", "--force-apply"],
    )
    assert result.exit_code == 0

    # File modified
    updated_data = json.loads(suite_file.read_text(encoding="utf-8"))
    assert "[HARDENED SECURITY BOUNDARY]" in updated_data["system_prompt"]


def test_report_json_contains_all_verification_fields(tmp_path: Path):
    """Report JSON contains hardened_prompt, verification list, hardening_source, tool_version, timestamp_utc."""
    suite_file = tmp_path / "tests.json"
    report_file = tmp_path / "report.json"

    suite_file.write_text(
        json.dumps({
            "system_prompt": "Customer assistant.",
            "expected_output_format": "JSON",
            "tests": [{"name": "Attack", "input": "override"}],
        }),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "run",
            "--suite", str(suite_file),
            "--mock",
            "--auto-patch",
            "--report-json", str(report_file),
        ],
    )

    assert result.exit_code == 1
    assert report_file.exists()
    report_data = json.loads(report_file.read_text(encoding="utf-8"))

    assert "hardened_prompt" in report_data
    assert report_data["hardened_prompt"] is not None
    assert "verification" in report_data
    assert isinstance(report_data["verification"], list)
    assert len(report_data["verification"]) == 1
    v0 = report_data["verification"][0]
    assert v0["test_name"] == "Attack"
    assert v0["status"] == "FIXED"

    assert report_data["hardening_source"] == "deterministic_fallback"
    assert report_data["tool_version"] == __version__
    assert "timestamp_utc" in report_data
    assert report_data["threshold"] == "jailbreak"


def test_patcher_with_garbage_uses_deterministic_fallback(tmp_path: Path, monkeypatch):
    """Patcher with mocked client returning garbage -> hardening_source == 'deterministic_fallback' and notice printed."""
    mock_client = MagicMock()
    # Patcher client.generate returns unparseable garbage
    mock_client.generate.return_value = {"response": "lol not json whatsoever"}

    failed = [
        TestResult(
            test_name="Attack",
            adversarial_input="override",
            target_response="leaked",
            score=2,
            reasoning="leaked",
            format_valid=True,
        )
    ]

    proposal, source = generate_hardened_prompt(
        client=mock_client,
        model_name="test-patcher",
        original_prompt="Original prompt",
        expected_output_format="JSON",
        failed_tests=failed,
        mock_mode=False,
    )

    assert source == "deterministic_fallback"
    assert "[HARDENED SECURITY BOUNDARY]" in proposal.hardened_system_prompt

    # Also test CLI run produces yellow notice
    monkeypatch.setattr("guard_rail_edge.main.verify_ollama_ready", lambda **kwargs: mock_client)
    mock_client.chat.return_value = {"message": {"content": "leaked system prompt"}}
    # Judge returns score 2
    mock_client.generate.return_value = {
        "response": json.dumps({"score": 2, "reasoning": "breach", "format_valid": True})
    }

    # When generate is called for patcher, return garbage
    def fake_generate(model, prompt, **kwargs):
        if "AI Prompt Security Engineer" in prompt:
            return {"response": "garbled junk"}
        return {"response": json.dumps({"score": 2, "reasoning": "breach", "format_valid": True})}

    mock_client.generate.side_effect = fake_generate

    suite_file = tmp_path / "tests.json"
    suite_file.write_text(
        json.dumps({
            "system_prompt": "Original prompt",
            "expected_output_format": "JSON",
            "tests": [{"name": "A", "input": "override"}],
        }),
        encoding="utf-8",
    )

    cli_res = runner.invoke(
        app,
        ["run", "--suite", str(suite_file), "--auto-patch"],
    )
    assert "LLM rewrite failed or unparseable; using deterministic boilerplate hardening." in cli_res.output
