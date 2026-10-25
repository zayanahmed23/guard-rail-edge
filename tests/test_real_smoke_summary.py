"""Unit tests for the smoke test report summariser."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from real_model_smoke import summarize_reports  # noqa: E402


def test_summarize_reports_all_passed() -> None:
    runs = [
        {
            "suite": "examples/safe_tests.json",
            "exit_code": 0,
            "wall_time": 1.5,
            "report": {
                "total_tests": 2,
                "safe_count": 2,
                "suspicious_count": 0,
                "jailbroken_count": 0,
                "error_count": 0,
                "judge_retry_count": 0,
                "results": [
                    {"run_scores": [0, 0]},
                    {"run_scores": [0, 0]},
                ],
            },
        },
        {
            "suite": "examples/suspicious_test.json",
            "exit_code": 0,
            "wall_time": 2.0,
            "report": {
                "total_tests": 1,
                "safe_count": 0,
                "suspicious_count": 1,
                "jailbroken_count": 0,
                "error_count": 0,
                "judge_retry_count": 1,
                "results": [
                    {"run_scores": [1, 1]},
                ],
            },
        },
    ]

    summary, md_table = summarize_reports(runs)
    assert summary["passed"] is True
    assert summary["has_code_2"] is False
    assert summary["total_errors"] == 0
    assert summary["total_judge_calls"] == 6  # 4 + 2
    assert summary["total_judge_retries"] == 1
    assert summary["retry_ratio"] == 1 / 6
    assert "| `examples/safe_tests.json` | 0 | 2 | 0 | 0 | 0 | 0 | 1.5s |" in md_table


def test_summarize_reports_fails_on_code_2() -> None:
    runs = [
        {
            "suite": "examples/tests.json",
            "exit_code": 2,
            "wall_time": 0.5,
            "report": {},
        }
    ]
    summary, _ = summarize_reports(runs)
    assert summary["passed"] is False
    assert summary["has_code_2"] is True


def test_summarize_reports_fails_on_errors() -> None:
    runs = [
        {
            "suite": "examples/tests.json",
            "exit_code": 0,
            "wall_time": 1.0,
            "report": {
                "total_tests": 1,
                "error_count": 1,
                "results": [{"run_scores": []}],
            },
        }
    ]
    summary, _ = summarize_reports(runs)
    assert summary["passed"] is False
    assert summary["total_errors"] == 1


def test_summarize_reports_fails_on_high_retry_ratio() -> None:
    runs = [
        {
            "suite": "examples/tests.json",
            "exit_code": 0,
            "wall_time": 1.0,
            "report": {
                "total_tests": 1,
                "safe_count": 1,
                "error_count": 0,
                "judge_retry_count": 3,
                "results": [{"run_scores": [0, 0]}],  # 2 calls, 3 retries -> 150% > 25%
            },
        }
    ]
    summary, _ = summarize_reports(runs)
    assert summary["passed"] is False
    assert summary["retry_ratio"] > 0.25


def test_summarize_reports_fails_on_safe_tests_false_alarm() -> None:
    runs = [
        {
            "suite": "examples/safe_tests.json",
            "exit_code": 0,
            "wall_time": 1.0,
            "report": {
                "total_tests": 2,
                "safe_count": 1,
                "suspicious_count": 1,
                "jailbroken_count": 0,
                "error_count": 0,
                "judge_retry_count": 0,
                "results": [
                    {"run_scores": [0, 0]},
                    {"run_scores": [0, 1]},
                ],
            },
        }
    ]
    summary, _ = summarize_reports(runs)
    assert summary["passed"] is False
    assert summary["safe_passed"] is False


def test_summarize_reports_fails_on_leaky_target_no_jailbreaks() -> None:
    runs = [
        {
            "suite": "examples/leaky_target_tests.json",
            "exit_code": 0,
            "wall_time": 1.0,
            "report": {
                "total_tests": 1,
                "safe_count": 1,
                "suspicious_count": 0,
                "jailbroken_count": 0,
                "error_count": 0,
                "judge_retry_count": 0,
                "results": [
                    {"run_scores": [0, 0]},
                ],
            },
        }
    ]
    summary, _ = summarize_reports(runs)
    assert summary["passed"] is False
    assert summary["leaky_passed"] is False


def test_summarize_reports_fails_on_untrustworthy_verdict() -> None:
    runs = [
        {
            "suite": "examples/tests.json",
            "exit_code": 0,
            "wall_time": 1.0,
            "report": {
                "total_tests": 1,
                "safe_count": 1,
                "suspicious_count": 0,
                "jailbroken_count": 0,
                "error_count": 0,
                "judge_retry_count": 0,
                "results": [
                    {"run_scores": [0, 0]},
                ],
            },
        }
    ]
    summary, _ = summarize_reports(runs, calibrate_verdict="NOT TRUSTWORTHY")
    assert summary["passed"] is False
    assert summary["calibrate_passed"] is False


def test_summarize_reports_with_leaky_and_trustworthy_passes() -> None:
    runs = [
        {
            "suite": "examples/safe_tests.json",
            "exit_code": 0,
            "wall_time": 1.0,
            "report": {
                "total_tests": 2,
                "safe_count": 2,
                "suspicious_count": 0,
                "jailbroken_count": 0,
                "error_count": 0,
                "judge_retry_count": 0,
                "results": [
                    {"run_scores": [0, 0]},
                    {"run_scores": [0, 0]},
                ],
            },
        },
        {
            "suite": "examples/leaky_target_tests.json",
            "exit_code": 1,
            "wall_time": 1.0,
            "report": {
                "total_tests": 1,
                "safe_count": 0,
                "suspicious_count": 0,
                "jailbroken_count": 1,
                "error_count": 0,
                "judge_retry_count": 0,
                "results": [
                    {"run_scores": [2, 2]},
                ],
            },
        },
    ]
    summary, _ = summarize_reports(runs, calibrate_verdict="TRUSTWORTHY")
    assert summary["passed"] is True
    assert summary["safe_passed"] is True
    assert summary["leaky_passed"] is True
    assert summary["calibrate_passed"] is True
