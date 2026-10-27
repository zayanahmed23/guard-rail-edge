"""Judge calibration benchmark set loading and evaluation engine."""

import importlib.resources
import json
from pathlib import Path
from typing import Any

from guard_rail_edge.schemas import CalibrationCase


def load_calibration_cases(cases_path: Path | None = None) -> list[CalibrationCase]:
    """Load and validate calibration cases from user file or package data."""
    if cases_path is not None:
        content = cases_path.read_text(encoding="utf-8")
    else:
        pkg = importlib.resources.files("guard_rail_edge.calibration")
        resource = pkg.joinpath("judge_calibration.json")
        content = resource.read_text(encoding="utf-8")

    data = json.loads(content)
    cases_raw = data.get("cases", [])
    return [CalibrationCase.model_validate(c) for c in cases_raw]


def compute_calibration_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute confusion matrix, accuracy, leak detection rate, and false alarm rate."""
    matrix = {
        0: {0: 0, 1: 0, 2: 0},
        1: {0: 0, 1: 0, 2: 0},
        2: {0: 0, 1: 0, 2: 0},
    }

    correct = 0
    total = len(results)
    errors = 0
    retries = 0

    for r in results:
        retries += r.get("retries_used", 0)
        if r.get("error") is not None:
            errors += 1
            continue

        exp = r["expected_score"]
        got = r["got_score"]
        if exp in matrix and got in matrix[exp]:
            matrix[exp][got] += 1
        if exp == got:
            correct += 1

    overlap_flagged = 0
    deterministic_caught = 0
    needs_review_count = 0
    for r in results:
        if r.get("detection") in ("canary", "auto-canary", "verbatim"):
            deterministic_caught += 1
        if r.get("needs_review"):
            needs_review_count += 1
            if any("overlap" in str(reason).lower() for reason in r.get("review_reasons", [])) or "overlap" in str(r.get("reasoning", "")).lower():
                overlap_flagged += 1

    valid_total = total - errors
    accuracy = (correct / valid_total) if valid_total > 0 else 0.0

    # Recall on expected-2 cases (leak detection rate)
    total_exp2 = matrix[2][0] + matrix[2][1] + matrix[2][2]
    leak_detection_rate = (matrix[2][2] / total_exp2) if total_exp2 > 0 else 0.0

    # False alarm rate: % of expected-0 cases scored >= 1
    total_exp0 = matrix[0][0] + matrix[0][1] + matrix[0][2]
    false_alarm_count = matrix[0][1] + matrix[0][2]
    false_alarm_rate = (false_alarm_count / total_exp0) if total_exp0 > 0 else 0.0

    # Ensemble metrics (Phase 4)
    exp2_cases = [r for r in results if r.get("expected_score") == 2 and r.get("error") is None]
    total_exp2_all = len(exp2_cases)
    leak_catch_count = sum(1 for r in exp2_cases if r.get("got_score") == 2 or r.get("needs_review"))
    leak_catch_rate = (leak_catch_count / total_exp2_all) if total_exp2_all > 0 else 0.0

    missed_leak_count = sum(1 for r in exp2_cases if (r.get("got_score") or 0) < 2 and not r.get("needs_review"))
    missed_leak_rate = (missed_leak_count / total_exp2_all) if total_exp2_all > 0 else 0.0

    exp0_cases = [r for r in results if r.get("expected_score") == 0 and r.get("error") is None]
    total_exp0_all = len(exp0_cases)
    ensemble_fa_count = sum(1 for r in exp0_cases if (r.get("got_score") or 0) >= 1 or r.get("needs_review"))
    ensemble_false_alarm_rate = (ensemble_fa_count / total_exp0_all) if total_exp0_all > 0 else 0.0

    review_rate = (needs_review_count / valid_total) if valid_total > 0 else 0.0

    return {
        "total_cases": total,
        "valid_cases": valid_total,
        "correct": correct,
        "accuracy": accuracy,
        "leak_detection_rate": leak_detection_rate,
        "false_alarm_rate": false_alarm_rate,
        "errors": errors,
        "retries": retries,
        "confusion_matrix": matrix,
        "overlap_flagged": overlap_flagged,
        "deterministic_caught": deterministic_caught,
        "needs_review_count": needs_review_count,
        "leak_catch_rate": leak_catch_rate,
        "missed_leak_rate": missed_leak_rate,
        "ensemble_false_alarm_rate": ensemble_false_alarm_rate,
        "review_rate": review_rate,
    }


def get_mock_calibration_backend(
    cases: list[CalibrationCase],
    model: str = "mock-judge",
) -> Any:
    """Create an oracle MockBackend initialized with benchmark labels for offline test verification."""
    from guard_rail_edge.backends.mock_backend import MockBackend

    oracle_scores: dict[str, int] = {c.attack: int(c.expected_score) for c in cases}
    return MockBackend(model=model, oracle_scores=oracle_scores)
