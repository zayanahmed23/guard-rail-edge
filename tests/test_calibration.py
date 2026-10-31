"""Tests for judge calibration dataset, metrics calculation, and calibrate CLI command."""

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from guard_rail_edge.calibration import (
    compute_calibration_metrics,
    load_calibration_cases,
)
from guard_rail_edge.evaluator import (
    EvaluationError,
    EvaluationScore,
    check_deterministic_leaks,
    check_deterministic_success,
)
from guard_rail_edge.main import app

runner = CliRunner(env={"COLUMNS": "200", "NO_COLOR": "1"})


def test_calibration_dataset_validates():
    """Verify calibration dataset loads, has 40-60 cases, unique IDs, and balanced scores."""
    cases = load_calibration_cases()
    assert 40 <= len(cases) <= 60, f"Expected 40-60 cases, got {len(cases)}"

    # Unique IDs
    ids = [c.id for c in cases]
    assert len(ids) == len(set(ids)), f"Duplicate case IDs found: {ids}"

    # Score balance: ~40% 0, ~20% 1, ~40% 2 (within +-10% of total)
    total = len(cases)
    count_0 = sum(1 for c in cases if c.expected_score == 0)
    count_1 = sum(1 for c in cases if c.expected_score == 1)
    count_2 = sum(1 for c in cases if c.expected_score == 2)

    pct_0 = count_0 / total
    pct_1 = count_1 / total
    pct_2 = count_2 / total

    assert 0.30 <= pct_0 <= 0.50, f"Expected 0 fraction out of [0.30, 0.50], got {pct_0:.2f}"
    assert 0.10 <= pct_1 <= 0.30, f"Expected 1 fraction out of [0.10, 0.30], got {pct_1:.2f}"
    assert 0.30 <= pct_2 <= 0.50, f"Expected 2 fraction out of [0.30, 0.50], got {pct_2:.2f}"

    # Split breakdown
    splits = {c.split for c in cases}
    assert "dev" in splits
    assert "holdout" in splits


def test_deterministic_checks_do_not_catch_all_expected_2_cases():
    """At least 60% of expected-2 cases must NOT be caught by deterministic checks."""
    cases = load_calibration_cases()
    exp2_cases = [c for c in cases if c.expected_score == 2]
    assert len(exp2_cases) > 0

    det_caught = 0
    for c in exp2_cases:
        res_succ = check_deterministic_success(c.target_response)
        res_leak = check_deterministic_leaks(c.system_prompt, c.target_response)
        if res_succ is not None or res_leak is not None:
            det_caught += 1

    not_caught = len(exp2_cases) - det_caught
    not_caught_ratio = not_caught / len(exp2_cases)
    assert not_caught_ratio >= 0.60, (
        f"Expected at least 60% of score-2 cases to require judge, got {not_caught_ratio:.1%}"
    )


def test_compute_calibration_metrics():
    """Test metric computations for accuracy, leak detection, and false alarm rate."""
    sample_results = [
        {"expected_score": 0, "got_score": 0, "retries_used": 0, "error": None},
        {"expected_score": 0, "got_score": 1, "retries_used": 0, "error": None},  # false alarm
        {"expected_score": 1, "got_score": 1, "retries_used": 1, "error": None},
        {"expected_score": 2, "got_score": 2, "retries_used": 0, "error": None},  # detected leak
        {"expected_score": 2, "got_score": 0, "retries_used": 0, "error": None},  # missed leak
    ]
    metrics = compute_calibration_metrics(sample_results)
    assert metrics["total_cases"] == 5
    assert metrics["valid_cases"] == 5
    assert metrics["correct"] == 3
    assert metrics["accuracy"] == 0.6
    assert metrics["leak_detection_rate"] == 0.5  # 1 of 2
    assert metrics["false_alarm_rate"] == 0.5  # 1 of 2
    assert metrics["errors"] == 0
    assert metrics["retries"] == 1


def test_calibrate_mock_clean_run(tmp_path: Path):
    """calibrate --mock runs to completion with 100% accuracy and TRUSTWORTHY verdict."""
    report_file = tmp_path / "cal_report.json"
    result = runner.invoke(app, ["calibrate", "--mock", "--report-json", str(report_file)])

    assert result.exit_code == 0, f"Failed with output:\n{result.output}"
    assert "TRUSTWORTHY" in result.output
    assert "Confusion Matrix" in result.output

    assert report_file.exists()
    data = json.loads(report_file.read_text(encoding="utf-8"))
    assert data["verdict"] == "TRUSTWORTHY"
    assert data["passed"] is True
    assert data["metrics_overall"]["accuracy"] == 1.0
    assert data["metrics_overall"]["leak_detection_rate"] == 1.0
    assert data["metrics_overall"]["false_alarm_rate"] == 0.0
    assert "leak_detection_ci" in data["metrics_overall"]
    assert "false_alarm_ci" in data["metrics_overall"]
    assert "judge_parse_retries" in data
    assert "rate_limit_waits" in data
    assert "elapsed_seconds" in data
    assert isinstance(data["elapsed_seconds"], (int, float))
    assert data["elapsed_seconds"] >= 0.0
    assert "Judge Parse Retries" in result.output
    assert "Rate-Limit Waits" in result.output


def test_calibrate_report_json_includes_elapsed_seconds(tmp_path: Path):
    """Assert calibrate --report-json output includes elapsed_seconds with fake/mock backend."""
    report_file = tmp_path / "timed_report.json"
    result = runner.invoke(app, ["calibrate", "--mock", "--report-json", str(report_file)])
    assert result.exit_code == 0
    assert report_file.exists()
    data = json.loads(report_file.read_text(encoding="utf-8"))
    assert "elapsed_seconds" in data
    assert isinstance(data["elapsed_seconds"], (int, float))
    assert data["elapsed_seconds"] >= 0.0


def test_calibrate_mock_judge_always_returns_one(monkeypatch, tmp_path: Path):
    """Mock judge that always returns 1 fails thresholds -> NOT TRUSTWORTHY, exit 1."""
    # When grade_interaction is called, return score 1 (simulating broken judge)
    def fake_grade(*args, **kwargs):
        return EvaluationScore(
            score=1,
            reasoning="Judge always suspicious",
            format_valid=True,
            detection="judge",
        )

    monkeypatch.setattr("guard_rail_edge.main.grade_interaction", fake_grade)

    report_file = tmp_path / "bad_report.json"
    result = runner.invoke(app, ["calibrate", "--mock", "--report-json", str(report_file)])

    assert result.exit_code == 1
    assert "NOT TRUSTWORTHY" in result.output
    assert "Failed thresholds" in result.output

    assert report_file.exists()
    data = json.loads(report_file.read_text(encoding="utf-8"))
    assert data["verdict"] == "NOT TRUSTWORTHY"
    assert data["passed"] is False
    # All cases scored 1, so leak detection rate for score 2 is 0.0
    assert data["metrics_overall"]["leak_detection_rate"] == 0.0
    # Expected 0 cases all got 1, so false alarm rate is 1.0 (100%)
    assert data["metrics_overall"]["false_alarm_rate"] == 1.0


def test_calibrate_mock_judge_raises_error(monkeypatch):
    """Mock judge raising EvaluationError terminates with exit code 2."""
    def raise_err(*args, **kwargs):
        raise EvaluationError("Judge connection completely dropped")

    monkeypatch.setattr("guard_rail_edge.main.grade_interaction", raise_err)

    result = runner.invoke(app, ["calibrate", "--mock"])
    assert result.exit_code == 2
    assert "Evaluator Error" in result.output or "Judge connection completely dropped" in result.output



def test_calibrate_invalid_cases_file(tmp_path: Path):
    """Non-existent or malformed cases file causes exit code 2."""
    bad_file = tmp_path / "non_existent.json"
    result = runner.invoke(app, ["calibrate", "--mock", "--cases", str(bad_file)])
    assert result.exit_code == 2
    assert "Error loading calibration cases" in result.output


@pytest.mark.slow
def test_wheel_contains_calibration_package_data(tmp_path: Path):
    """Assert built wheel package contains guard_rail_edge/calibration/judge_calibration.json."""
    import importlib.util
    import shutil

    if not importlib.util.find_spec("build"):
        pytest.skip("build module not installed in test environment")

    repo_root = Path(__file__).parent.parent
    src_dir = tmp_path / "src"
    out_dir = tmp_path / "dist"

    def ignore_patterns(path: str, names: list[str]) -> set[str]:
        ignored = set()
        for name in names:
            if name in (
                ".git",
                "build",
                "dist",
                ".venv",
                "venv",
                "env",
                "__pycache__",
                ".pytest_cache",
                ".mypy_cache",
                ".ruff_cache",
            ):
                ignored.add(name)
            elif name.endswith(".egg-info"):
                ignored.add(name)
        return ignored

    shutil.copytree(repo_root, src_dir, ignore=ignore_patterns)

    res = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(out_dir)],
        cwd=str(src_dir),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Failed to build wheel:\n{res.stderr}"

    wheel_files = list(out_dir.glob("*.whl"))
    assert len(wheel_files) == 1

    with zipfile.ZipFile(wheel_files[0], "r") as z:
        names = z.namelist()

    expected_cal_file = "guard_rail_edge/calibration/judge_calibration.json"
    assert any(expected_cal_file in name for name in names), (
        f"Calibration JSON not found in wheel archive! Contents: {names}"
    )


def test_verdict_dual_threshold_overall_and_holdout():
    """Verify TRUSTWORTHY requires both overall and holdout sets to satisfy thresholds."""
    from guard_rail_edge.calibration import evaluate_calibration_verdict

    # 1. Holdout passes, but overall fails false alarm threshold
    m_overall_fail = {
        "total_cases": 50,
        "leak_detection_rate": 1.0,
        "false_alarm_rate": 0.35,  # Fails > 0.15
        "errors": 0,
    }
    m_holdout_pass = {
        "total_cases": 20,
        "leak_detection_rate": 1.0,
        "false_alarm_rate": 0.125,  # Passes <= 0.15
        "errors": 0,
    }
    passed, failed = evaluate_calibration_verdict(m_overall_fail, m_holdout_pass, is_ensemble=False)
    assert passed is False
    assert any("overall false alarm rate 35.0% > 15.0%" in f for f in failed)

    # 2. Both pass
    m_overall_pass = {
        "total_cases": 50,
        "leak_detection_rate": 1.0,
        "false_alarm_rate": 0.05,
        "errors": 0,
    }
    passed2, failed2 = evaluate_calibration_verdict(m_overall_pass, m_holdout_pass, is_ensemble=False)
    assert passed2 is True
    assert failed2 == []


def test_rescore_committed_gpt_oss_report():
    """Rescoring committed gpt-oss report yields NOT TRUSTWORTHY with overall false alarm failure."""
    raw_path = Path("docs/data/raw/openai_gpt-oss-120b.json")
    assert raw_path.is_file()

    result = runner.invoke(app, ["calibrate", "--rescore", str(raw_path)])
    assert result.exit_code == 1
    assert "NOT TRUSTWORTHY" in result.output
    assert "overall false alarm rate 35.0% > 15.0%" in result.output


def test_rescore_never_calls_backend(monkeypatch):
    """Assert --rescore recomputes metrics without ever initializing or invoking backend."""
    def poisoned_get_backend(*args, **kwargs):
        raise AssertionError("get_backend was called during calibrate --rescore!")

    monkeypatch.setattr("guard_rail_edge.backends.get_backend", poisoned_get_backend)

    raw_path = Path("docs/data/raw/qwen_qwen3.8-27b.json")
    result = runner.invoke(app, ["calibrate", "--rescore", str(raw_path)])
    assert result.exit_code == 0
    assert "TRUSTWORTHY" in result.output

