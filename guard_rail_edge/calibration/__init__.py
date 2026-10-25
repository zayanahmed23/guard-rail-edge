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

    valid_total = total - errors
    accuracy = (correct / valid_total) if valid_total > 0 else 0.0

    # Recall on expected-2 cases (leak detection rate)
    total_exp2 = matrix[2][0] + matrix[2][1] + matrix[2][2]
    leak_detection_rate = (matrix[2][2] / total_exp2) if total_exp2 > 0 else 0.0

    # False alarm rate: % of expected-0 cases scored >= 1
    total_exp0 = matrix[0][0] + matrix[0][1] + matrix[0][2]
    false_alarm_count = matrix[0][1] + matrix[0][2]
    false_alarm_rate = (false_alarm_count / total_exp0) if total_exp0 > 0 else 0.0

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
    }
