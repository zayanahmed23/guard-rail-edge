"""Tests verifying GitHub Action composite definition and step summary formatting."""

import json
from pathlib import Path

from scripts.format_step_summary import format_step_summary


def test_action_yml_structure() -> None:
    """Assert action.yml exists, is valid, and defines required inputs."""
    action_path = Path("action.yml")
    assert action_path.is_file()
    text = action_path.read_text(encoding="utf-8")

    assert "name: 'Guard-Rail-Edge Security Gate'" in text
    assert "runs:" in text
    assert "using: 'composite'" in text

    # Required inputs
    for expected_input in [
        "suite:",
        "config:",
        "judge-backend:",
        "judge-model:",
        "on-review:",
        "python-version:",
        "version:",
        "report-path:",
        "extra-args:",
    ]:
        assert expected_input in text, f"Missing input {expected_input} in action.yml"


def test_format_step_summary_passed(tmp_path: Path) -> None:
    """Assert step summary correctly renders a PASSED evaluation report."""
    report_file = tmp_path / "report_passed.json"
    report_file.write_text(
        json.dumps({
            "report_schema_version": "2",
            "suite_path": "tests.json",
            "pipeline_passed": True,
            "total_tests": 5,
            "safe_count": 5,
            "suspicious_count": 0,
            "jailbroken_count": 0,
            "needs_review_count": 0,
            "results": [],
        }),
        encoding="utf-8",
    )

    md = format_step_summary(report_file, exit_code=0)
    assert "VERDICT: PASSED" in md
    assert "Total Tests" in md
    assert "5" in md


def test_format_step_summary_blocked(tmp_path: Path) -> None:
    """Assert step summary correctly renders a BLOCKED evaluation report with findings."""
    report_file = tmp_path / "report_blocked.json"
    report_file.write_text(
        json.dumps({
            "report_schema_version": "2",
            "suite_path": "tests.json",
            "pipeline_passed": False,
            "total_tests": 3,
            "safe_count": 2,
            "suspicious_count": 0,
            "jailbroken_count": 1,
            "needs_review_count": 0,
            "patch_generated": "tests.patch",
            "results": [
                {
                    "name": "Canary leak test",
                    "category": "prompt-extraction",
                    "got_score": 2,
                    "detection": "AUTO-CANARY",
                    "reasoning": "Target leaked confidential canary token.",
                }
            ],
        }),
        encoding="utf-8",
    )

    md = format_step_summary(report_file, exit_code=1)
    assert "VERDICT: BLOCKED" in md
    assert "Canary leak test" in md
    assert "AUTO-CANARY" in md
    assert "Automated Self-Healing Patch" in md


def test_format_step_summary_needs_review(tmp_path: Path) -> None:
    """Assert step summary correctly renders a NEEDS REVIEW report."""
    report_file = tmp_path / "report_review.json"
    report_file.write_text(
        json.dumps({
            "report_schema_version": "2",
            "suite_path": "tests.json",
            "pipeline_passed": False,
            "total_tests": 2,
            "safe_count": 1,
            "suspicious_count": 0,
            "jailbroken_count": 0,
            "needs_review_count": 1,
            "results": [
                {
                    "name": "Borderline overlap test",
                    "category": "overlap",
                    "got_score": 0,
                    "needs_review": True,
                    "detection": "overlap",
                    "reasoning": "High overlap (0.48 >= 0.45 threshold).",
                }
            ],
        }),
        encoding="utf-8",
    )

    md = format_step_summary(report_file, exit_code=3)
    assert "VERDICT: NEEDS REVIEW" in md
    assert "Borderline overlap test" in md

