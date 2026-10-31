"""Tests verifying integrity and provenance of benchmark calibration results.

Every calibration row must derive from committed raw reports or archived legacy commits.
No fabricated numbers or prohibited models are permitted.
"""

import json
import math
import re
import subprocess
import sys
from pathlib import Path

from guard_rail_edge.calibration import wilson_score_interval

PROHIBITED_MODELS = [
    "mistral:7b",
    "llama3:8b",
    "deepseek-r1:7b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]

SECRET_PATTERNS = [
    re.compile(r"gsk_[a-zA-Z0-9_\-]{20,}"),
    re.compile(r"sk-[a-zA-Z0-9_\-]{20,}"),
    re.compile(r"ghp_[a-zA-Z0-9_\-]{20,}"),
]


def test_build_results_check_passes() -> None:
    """Assert build_results.py --check succeeds, confirming tables match raw data."""
    repo_root = Path(__file__).resolve().parent.parent
    script_path = repo_root / "scripts" / "build_results.py"

    cmd = [sys.executable, str(script_path), "--check"]
    res = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True)
    assert res.returncode == 0, f"build_results.py --check failed:\nstdout: {res.stdout}\nstderr: {res.stderr}"
    assert "OK:" in res.stdout


def test_judge_calibration_provenance() -> None:
    """Assert every row in judge_calibration.json traces to a real raw report or legacy commit."""
    repo_root = Path(__file__).resolve().parent.parent
    data_path = repo_root / "docs" / "data" / "judge_calibration.json"
    legacy_path = repo_root / "docs" / "data" / "legacy_results.json"

    assert data_path.is_file()
    assert legacy_path.is_file()

    rows = json.loads(data_path.read_text(encoding="utf-8"))
    legacy_rows = {item["model"]: item for item in json.loads(legacy_path.read_text(encoding="utf-8"))}

    assert len(rows) >= 5, "Expected at least 5 benchmarked judge models"

    for row in rows:
        model = row["model"]
        is_legacy = row.get("is_legacy", False)

        if is_legacy:
            assert model in legacy_rows, f"Legacy model {model} not found in legacy_results.json"
            commit = row.get("source_commit", "")
            assert re.match(r"^[0-9a-f]{40}$", commit), f"Invalid source_commit for {model}: {commit}"
        else:
            source_file = row.get("source_file")
            assert source_file, f"Row for {model} missing source_file"
            raw_path = repo_root / source_file
            assert raw_path.is_file(), f"Raw report not found for {model}: {raw_path}"
            raw_data = json.loads(raw_path.read_text(encoding="utf-8"))
            assert raw_data.get("judge_model") == model, f"Model mismatch in raw report {raw_path}"


def test_wilson_intervals_recomputed_correctly() -> None:
    """Assert Wilson intervals in judge_calibration.json match n=20 formulation."""
    repo_root = Path(__file__).resolve().parent.parent
    data_path = repo_root / "docs" / "data" / "judge_calibration.json"
    rows = json.loads(data_path.read_text(encoding="utf-8"))

    # In 50-case benchmark, there are 20 score 2 (leaks) and 20 score 0 (benign)
    n_leaks = 20
    n_fa = 20

    for row in rows:
        model = row["model"]
        leak_rate = float(row["leak_detection_rate"])
        fa_rate = float(row["false_alarm_rate"])

        # Recompute expected intervals
        k_leak = round(leak_rate * n_leaks)
        expected_leak_ci = wilson_score_interval(k_leak, n_leaks)
        assert math.isclose(row["leak_ci_lower"], expected_leak_ci[0], abs_tol=1e-3), (
            f"{model} leak lower CI mismatch: {row['leak_ci_lower']} vs {expected_leak_ci[0]}"
        )
        assert math.isclose(row["leak_ci_upper"], expected_leak_ci[1], abs_tol=1e-3), (
            f"{model} leak upper CI mismatch: {row['leak_ci_upper']} vs {expected_leak_ci[1]}"
        )

        k_fa = round(fa_rate * n_fa)
        expected_fa_ci = wilson_score_interval(k_fa, n_fa)
        assert math.isclose(row["fa_ci_lower"], expected_fa_ci[0], abs_tol=1e-3), (
            f"{model} fa lower CI mismatch: {row['fa_ci_lower']} vs {expected_fa_ci[0]}"
        )
        assert math.isclose(row["fa_ci_upper"], expected_fa_ci[1], abs_tol=1e-3), (
            f"{model} fa upper CI mismatch: {row['fa_ci_upper']} vs {expected_fa_ci[1]}"
        )


def test_no_prohibited_models_in_results() -> None:
    """Assert none of the un-evaluated or fabricated models appear in results tables."""
    repo_root = Path(__file__).resolve().parent.parent
    judge_cal_path = repo_root / "docs" / "data" / "judge_calibration.json"
    real_results_path = repo_root / "docs" / "real-model-results.md"
    readme_path = repo_root / "README.md"

    judge_cal_text = judge_cal_path.read_text(encoding="utf-8")
    real_results_text = real_results_path.read_text(encoding="utf-8")
    readme_text = readme_path.read_text(encoding="utf-8")

    for prohibited in PROHIBITED_MODELS:
        assert prohibited not in judge_cal_text, f"Prohibited model '{prohibited}' found in judge_calibration.json"
        assert prohibited not in real_results_text, f"Prohibited model '{prohibited}' found in docs/real-model-results.md"
        assert prohibited not in readme_text, f"Prohibited model '{prohibited}' found in README.md"


def test_no_api_keys_in_raw_reports() -> None:
    """Assert no raw report in docs/data/raw/ leaks API keys or secrets."""
    repo_root = Path(__file__).resolve().parent.parent
    raw_dir = repo_root / "docs" / "data" / "raw"

    for json_file in raw_dir.glob("*.json"):
        text = json_file.read_text(encoding="utf-8")
        for pat in SECRET_PATTERNS:
            match = pat.search(text)
            assert not match, f"Secret pattern {pat.pattern} detected in {json_file}: {match.group(0)}"


def test_results_tables_contain_safe_review_column():
    """Assert generated tables in README and docs contain Safe cases sent to review column."""
    repo_root = Path(__file__).resolve().parent.parent
    readme_path = repo_root / "README.md"
    real_results_path = repo_root / "docs" / "real-model-results.md"

    readme_text = readme_path.read_text(encoding="utf-8")
    real_results_text = real_results_path.read_text(encoding="utf-8")

    assert "| Safe cases sent to review |" in readme_text
    assert "| Safe cases sent to review |" in real_results_text

    # Safe review counts from raw reports
    # qwen3.8-27b: 3/20 = 15.0%
    assert "**15.0%** (3/20)" in readme_text
    assert "**15.0%** (3/20)" in real_results_text

    # gpt-oss-120b: 1/20 = 5.0%
    assert "**5.0%** (1/20)" in readme_text
    assert "**5.0%** (1/20)" in real_results_text

    # README review warning notice
    assert "With `--on-review fail` (default), cases sent to review fail CI; use `--on-review warn` to report them without blocking." in readme_text


def test_gpt_variation_note_present():
    """Assert reasoning model non-determinism note appears in docs/real-model-results.md."""
    repo_root = Path(__file__).resolve().parent.parent
    real_results_path = repo_root / "docs" / "real-model-results.md"
    real_results_text = real_results_path.read_text(encoding="utf-8")

    assert "gpt-oss-120b's verdicts varied between runs on 5/50 cases" in real_results_text


def test_build_results_source_hygiene():
    """Assert build_results.py contains no literal wall-time regex match and no literal TRUSTWORTHY in row f-strings."""
    repo_root = Path(__file__).resolve().parent.parent
    build_script = repo_root / "scripts" / "build_results.py"
    source = build_script.read_text(encoding="utf-8")

    # 1. No literal wall-time pattern (\d+m \d+s)
    wall_match = re.search(r"\d+m \d+s", source)
    assert not wall_match, f"Found literal wall-time pattern in build_results.py: {wall_match.group(0)}"

    # 2. No literal TRUSTWORTHY inside table-row f-strings
    for line in source.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("lines.append(f") and "|" in trimmed:
            assert "TRUSTWORTHY" not in trimmed, f"Found literal 'TRUSTWORTHY' in table-row f-string: {line}"


def test_adding_raw_report_adds_new_row(tmp_path: Path):
    """Assert adding a copy of a raw report under a new model name produces a new row."""
    from scripts.build_results import generate_results_markdown_table, validate_raw_reports

    repo_root = Path(__file__).resolve().parent.parent
    raw_dir = repo_root / "docs" / "data" / "raw"

    # Copy existing raw reports into tmp_path
    tmp_raw = tmp_path / "raw"
    tmp_raw.mkdir(parents=True, exist_ok=True)
    for p in raw_dir.glob("*.json"):
        (tmp_raw / p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")

    # Add a copy under a new model name
    source_qwen = tmp_raw / "qwen_qwen3.8-27b.json"
    data = json.loads(source_qwen.read_text(encoding="utf-8"))
    data["judge_model"] = "custom-vendor/new-judge-model"
    (tmp_raw / "custom_vendor_new_judge.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    loaded_reports = validate_raw_reports(tmp_raw)
    table_md = generate_results_markdown_table(loaded_reports, [])

    assert "custom-vendor/new-judge-model" in table_md, "New model row did not appear in generated markdown table"


def test_legacy_rows_render_na():
    """Assert legacy rows render 'n/a' / 'n/a (not measured)' for safe review rate."""
    repo_root = Path(__file__).resolve().parent.parent
    readme_path = repo_root / "README.md"
    real_results_path = repo_root / "docs" / "real-model-results.md"

    readme_text = readme_path.read_text(encoding="utf-8")
    real_results_text = real_results_path.read_text(encoding="utf-8")

    assert "n/a (not measured)" in readme_text
    assert "n/a (not measured)" in real_results_text



