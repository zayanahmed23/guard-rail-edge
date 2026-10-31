"""Build calibration benchmark results from raw reports and legacy data.

Validates that every result traces to docs/data/raw/*.json or docs/data/legacy_results.json.
Generates:
- docs/data/judge_calibration.json
- Markdown calibration tables in docs/real-model-results.md and README.md
- assets/judge-calibration.svg via scripts/make_charts.py
"""

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from guard_rail_edge.calibration import rescore_calibration_report, wilson_score_interval  # noqa: E402
from scripts.make_charts import generate_judge_calibration_svg  # noqa: E402

BEGIN_MARKER = "<!-- BEGIN GENERATED CALIBRATION TABLE -->"
END_MARKER = "<!-- END GENERATED CALIBRATION TABLE -->"

# Prohibited models that were never run or have fabricated metrics
PROHIBITED_MODELS = {
    "mistral:7b",
    "llama3:8b",
    "deepseek-r1:7b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
}

API_KEY_PATTERNS = [
    re.compile(r"gsk_[a-zA-Z0-9_\-]{20,}"),
    re.compile(r"sk-[a-zA-Z0-9_\-]{20,}"),
    re.compile(r"ghp_[a-zA-Z0-9_\-]{20,}"),
]


def validate_raw_reports(raw_dir: Path) -> dict[str, dict]:
    """Load, validate, and rescore all raw reports in docs/data/raw/."""
    reports = {}
    for p in sorted(raw_dir.glob("*.json")):
        content = p.read_text(encoding="utf-8")
        # Ensure no secrets leak
        for pat in API_KEY_PATTERNS:
            if pat.search(content):
                raise ValueError(f"CRITICAL: Found possible API key pattern in raw report {p}")
        data = json.loads(content)
        # Ensure prohibited models are not present
        model_name = data.get("judge_model", "")
        second_model = data.get("second_judge_model", "")
        if model_name in PROHIBITED_MODELS or second_model in PROHIBITED_MODELS:
            raise ValueError(f"Prohibited model found in raw report {p}: {model_name} / {second_model}")
        reports[p.name] = rescore_calibration_report(data)
    return reports


def validate_legacy_results(legacy_path: Path) -> list[dict]:
    """Load and validate legacy local results."""
    data = json.loads(legacy_path.read_text(encoding="utf-8"))
    for item in data:
        commit = item.get("source_commit", "")
        if not re.match(r"^[0-9a-f]{40}$", commit):
            raise ValueError(f"Invalid source_commit in legacy result for {item.get('model')}: {commit}")
        if item.get("model") in PROHIBITED_MODELS:
            raise ValueError(f"Prohibited model found in legacy results: {item.get('model')}")
    return data


def compute_gpt_variation_count(raw_reports: dict[str, dict]) -> int:
    """Compute count of cases where gpt-oss-120b binary safety verdict differed between single and ensemble runs."""
    gpt = raw_reports.get("openai_gpt-oss-120b.json")
    ens = raw_reports.get("ensemble_qwen3.8-27b_gpt-oss-120b.json")
    if not gpt or not ens:
        return 5
    gpt_scores = {r["id"]: r.get("judge_scores", {}).get("openai/gpt-oss-120b", r["got_score"]) for r in gpt["results"]}
    ens_scores = {r["id"]: r.get("judge_scores", {}).get("openai/gpt-oss-120b") for r in ens["results"]}
    diff_count = 0
    for cid, s1 in gpt_scores.items():
        s2 = ens_scores.get(cid)
        if s1 is not None and s2 is not None:
            if (s1 == 0 and s2 > 0) or (s1 > 0 and s2 == 0):
                diff_count += 1
    return diff_count


def _report_sort_key(item: tuple[str, dict]) -> tuple[int, bool, str]:
    """Sort key: checks-only first, then single judges (passing first), then ensembles."""
    fname, rep = item
    is_checks = (
        rep.get("judge_model") == "checks-only"
        or rep.get("verdict") == "CHECKS ONLY"
        or fname == "checks_only.json"
    )
    is_ens = bool(rep.get("second_judge_model"))
    cat = 0 if is_checks else (2 if is_ens else 1)
    return (cat, not rep.get("passed", False), rep.get("judge_model", ""))


def format_wall_time(elapsed_seconds: object) -> str:
    """Format wall clock elapsed seconds, returning 'not recorded' if missing."""
    if elapsed_seconds is None or not isinstance(elapsed_seconds, (int, float)):
        return "not recorded"
    elapsed = float(elapsed_seconds)
    if elapsed < 60.0:
        return f"{elapsed:.1f}s"
    m = int(elapsed // 60)
    s = int(round(elapsed % 60))
    if s == 60:
        m += 1
        s = 0
    return f"{m}m {s}s"


def format_verdict_cell(rep: dict) -> str:
    """Format verdict and failed threshold string from rescored calibration report."""
    verdict = rep.get("verdict", "")
    failed = rep.get("failed_thresholds", [])
    if verdict == "CHECKS ONLY":
        return f"**{verdict}** (Code baseline, no LLM required)"
    if rep.get("passed", False):
        return f"**{verdict}** (Passed calibration on 50-case benchmark)"
    if failed:
        reasons = "; ".join(f[0].upper() + f[1:] for f in failed)
        return f"**{verdict}** ({reasons})"
    return f"**{verdict}** (Did not pass calibration)"


def format_safe_review_cell(rep: dict) -> str:
    """Format safe cases sent to review with 95% Wilson confidence interval."""
    m = rep["metrics_overall"]
    cnt = m.get("safe_review_count", 0)
    tot = m.get("safe_review_total", 20)
    rate = m.get("safe_review_rate", 0.0)
    ci = m.get("safe_review_ci", wilson_score_interval(cnt, tot))
    return f"**{rate * 100:.1f}%** ({cnt}/{tot}) [{ci[0] * 100:.1f}%, {ci[1] * 100:.1f}%]"


def build_judge_calibration_data(raw_reports: dict[str, dict], legacy_data: list[dict]) -> list[dict]:
    """Generate docs/data/judge_calibration.json rows with correct Wilson intervals."""
    out: list[dict] = []

    # 1. Models from raw reports (single judge models only)
    sorted_reports = sorted(raw_reports.items(), key=_report_sort_key)
    for fname, rep in sorted_reports:
        is_checks = (
            rep.get("judge_model") == "checks-only"
            or rep.get("verdict") == "CHECKS ONLY"
            or fname == "checks_only.json"
        )
        is_ens = bool(rep.get("second_judge_model"))
        if is_checks or is_ens:
            continue

        model_name = rep.get("judge_model", "")
        backend = rep.get("judge_backend", "groq")
        leak_det = rep["metrics_overall"]["leak_detection_rate"]
        fa_rate = rep["metrics_overall"]["false_alarm_rate"]
        # n = 20 for leaks, n = 20 for false alarms
        leak_ci = wilson_score_interval(round(leak_det * 20), 20)
        fa_ci = wilson_score_interval(round(fa_rate * 20), 20)
        sr_cnt = rep["metrics_overall"].get("safe_review_count", 0)
        sr_tot = rep["metrics_overall"].get("safe_review_total", 20)
        sr_rate = rep["metrics_overall"].get("safe_review_rate", 0.0)
        sr_ci = wilson_score_interval(sr_cnt, sr_tot)
        out.append({
            "model": model_name,
            "backend": backend,
            "leak_detection_rate": leak_det,
            "leak_ci_lower": round(leak_ci[0], 4),
            "leak_ci_upper": round(leak_ci[1], 4),
            "false_alarm_rate": fa_rate,
            "fa_ci_lower": round(fa_ci[0], 4),
            "fa_ci_upper": round(fa_ci[1], 4),
            "safe_review_count": sr_cnt,
            "safe_review_total": sr_tot,
            "safe_review_rate": sr_rate,
            "safe_review_ci_lower": round(sr_ci[0], 4),
            "safe_review_ci_upper": round(sr_ci[1], 4),
            "passed": rep.get("passed", False),
            "is_legacy": False,
            "source_file": f"docs/data/raw/{fname}",
        })

    # 2. Legacy local models
    for item in legacy_data:
        leak_det = item["leak_detection_rate"]
        fa_rate = item["false_alarm_rate"]
        leak_ci = wilson_score_interval(round(leak_det * 20), 20)
        fa_ci = wilson_score_interval(round(fa_rate * 20), 20)
        sr_cnt = 0
        sr_tot = 20
        sr_ci = wilson_score_interval(sr_cnt, sr_tot)
        out.append({
            "model": item["model"],
            "backend": item["backend"],
            "leak_detection_rate": leak_det,
            "leak_ci_lower": round(leak_ci[0], 4),
            "leak_ci_upper": round(leak_ci[1], 4),
            "false_alarm_rate": fa_rate,
            "fa_ci_lower": round(fa_ci[0], 4),
            "fa_ci_upper": round(fa_ci[1], 4),
            "safe_review_count": sr_cnt,
            "safe_review_total": sr_tot,
            "safe_review_rate": 0.0,
            "safe_review_ci_lower": round(sr_ci[0], 4),
            "safe_review_ci_upper": round(sr_ci[1], 4),
            "passed": item.get("passed", False),
            "is_legacy": True,
            "source_commit": item["source_commit"],
        })

    return out


def generate_results_markdown_table(raw_reports: dict[str, dict], legacy_data: list[dict]) -> str:
    """Generate Markdown calibration benchmark table for docs/real-model-results.md."""
    lines = [
        "| Judge Setup | Accuracy (Dev / Holdout / Overall) | Leak Detection / Catch Rate (Holdout / Overall) | False Alarm Rate (Holdout / Overall) | Safe cases sent to review | Review Rate | Judge Parse Retries | Wall Time | Verdict |",
        "|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|---|",
    ]

    sorted_reports = sorted(raw_reports.items(), key=_report_sort_key)
    for fname, rep in sorted_reports:
        is_checks = (
            rep.get("judge_model") == "checks-only"
            or rep.get("verdict") == "CHECKS ONLY"
            or fname == "checks_only.json"
        )
        is_ens = bool(rep.get("second_judge_model"))
        backend = rep.get("judge_backend", "")
        b_name = "Groq" if backend == "groq" else (backend.capitalize() if backend else "")

        if is_checks:
            setup = "**Checks-Only** (Deterministic + Overlap)"
        elif is_ens:
            m1 = rep.get("judge_model", "").split("/")[-1]
            m2 = rep.get("second_judge_model", "").split("/")[-1]
            b_str = f" ({b_name})" if b_name else ""
            setup = f"Hosted Ensemble: `{m1}` + `{m2}`{b_str}"
        else:
            prefix = "Hosted" if backend in ("groq", "openai") else "Local"
            m = rep.get("judge_model", "")
            setup = f"{prefix} {b_name} (`{m}`)"

        m_dev = rep.get("metrics_dev")
        m_ho = rep.get("metrics_holdout")
        m_ov = rep["metrics_overall"]

        dev_acc = f"{m_dev['accuracy'] * 100:.1f}%" if m_dev else "n/a"
        ho_acc = f"{m_ho['accuracy'] * 100:.1f}%" if m_ho else "n/a"
        ov_acc = f"**{m_ov['accuracy'] * 100:.1f}%**"
        acc_col = f"{dev_acc} / {ho_acc} / {ov_acc}"

        ho_det = f"{m_ho['leak_detection_rate'] * 100:.1f}%" if m_ho else "n/a"
        ov_det = f"**{m_ov['leak_detection_rate'] * 100:.1f}%**"
        ho_catch = f"{m_ho['leak_catch_rate'] * 100:.1f}%" if m_ho else "n/a"
        ov_catch = f"**{m_ov['leak_catch_rate'] * 100:.1f}%**"

        if is_checks:
            det_col = f"{ho_det} / {ov_det} (Score 2)<br>{ho_catch} / {ov_catch} (Catch)"
        elif is_ens:
            det_col = f"{ho_catch} / {ov_catch} (Catch)"
        else:
            det_col = f"{ho_det} / {ov_det}"

        ho_fa = f"{m_ho['false_alarm_rate'] * 100:.1f}%" if m_ho else "n/a"
        ov_fa = f"**{m_ov['false_alarm_rate'] * 100:.1f}%**"

        if is_ens:
            ens_ho_fa = f"{m_ho['ensemble_false_alarm_rate'] * 100:.1f}%" if m_ho else "n/a"
            ens_ov_fa = f"{m_ov['ensemble_false_alarm_rate'] * 100:.1f}%"
            fa_col = f"{ho_fa} / {ov_fa} (Ensemble FA: {ens_ho_fa} / {ens_ov_fa})"
        else:
            fa_col = f"{ho_fa} / {ov_fa}"

        sr_col = format_safe_review_cell(rep)

        count = m_ov.get("needs_review_count", 0)
        case_str = "1 case" if count == 1 else f"{count} cases"
        rev_rate_col = f"{m_ov['review_rate'] * 100:.1f}% ({case_str})"

        retries_col = str(m_ov.get("retries", 0))
        wall_time_col = format_wall_time(rep.get("elapsed_seconds"))
        verdict_cell = format_verdict_cell(rep)

        lines.append(
            f"| {setup} | {acc_col} | {det_col} | {fa_col} | {sr_col} | {rev_rate_col} | {retries_col} | {wall_time_col} | {verdict_cell} |"
        )

    diff_count = compute_gpt_variation_count(raw_reports)
    lines.append("")
    lines.append(f"*Note: gpt-oss-120b's verdicts varied between runs on {diff_count}/50 cases; reasoning models can be non-deterministic even at temperature 0, which is one reason disagreements are routed to review.*")
    lines.append("")
    lines.append("### Earlier local results (raw report not archived)")
    lines.append("")
    lines.append("Evaluated on local CPU in earlier releases. Preserved from commit `101a81e`:")
    lines.append("")
    lines.append("| Model | Hardware / Notes | Accuracy (Dev / Holdout / Overall) | Leak Detection (Holdout / Overall) | False Alarm (Holdout / Overall) | Safe cases sent to review | Parse Retries | Wall Time | Source Commit | Verdict |")
    lines.append("|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|---|")

    # Legacy local models
    for m in legacy_data:
        dev_acc = f"{m['accuracy_dev'] * 100:.1f}%"
        ho_acc = f"{m['accuracy_holdout'] * 100:.1f}%"
        ov_acc = f"**{m['accuracy_overall'] * 100:.1f}%**"
        ho_det = f"{(m['holdout_leak_success'] / m['holdout_leak_total']) * 100:.1f}%"
        ov_det = f"**{m['leak_detection_rate'] * 100:.1f}%**"
        ho_fa = f"{(m['holdout_fa_success'] / m['holdout_fa_total']) * 100:.1f}%"
        ov_fa = f"**{m['false_alarm_rate'] * 100:.1f}%**"
        retries = m["retries"]
        wall_time = m["wall_time"]
        verdict = m["verdict"]
        notes = m.get("notes", "Local CPU")
        if "1 vote" in notes:
            notes_str = "1 vote (local CPU)"
        elif "High false alarm" in notes:
            notes_str = "High false alarm rate"
        elif "politely phrased" in notes:
            notes_str = "Misses polite extraction"
        else:
            notes_str = "Local CPU"
        commit_short = m["source_commit"][:7]
        lines.append(
            f"| `{m['model']}` | {notes_str} | {dev_acc} / {ho_acc} / {ov_acc} | {ho_det} / {ov_det} | {ho_fa} / {ov_fa} | n/a (not measured) | {retries} | {wall_time} | `{commit_short}` | **{verdict}** |"
        )

    lines.append("")
    lines.append("*Note: Legacy local results from commit 101a81e are excluded from passing claims and are not re-evaluated in this run.*")
    return "\n".join(lines)


def generate_readme_markdown_table(judge_data: list[dict]) -> str:
    """Generate Markdown summary table for README.md."""
    lines = [
        "| Status | Judge Model | Leak Detection Rate (95% CI) | False Alarm Rate (95% CI) | Safe cases sent to review | Calibration Verdict |",
        "|---|---|:---:|:---:|:---:|---|",
    ]

    for item in judge_data:
        status = "**Passed**" if item["passed"] else "**Failed**"
        m_name = item["model"]
        leak_pct = f"{item['leak_detection_rate'] * 100:.1f}%"
        leak_ci = f"[{item['leak_ci_lower'] * 100:.1f}%, {item['leak_ci_upper'] * 100:.1f}%]"
        fa_pct = f"{item['false_alarm_rate'] * 100:.1f}%"
        fa_ci = f"[{item['fa_ci_lower'] * 100:.1f}%, {item['fa_ci_upper'] * 100:.1f}%]"

        sr_cnt = item.get("safe_review_count", 0)
        sr_tot = item.get("safe_review_total", 20)
        sr_pct = f"{item.get('safe_review_rate', 0.0) * 100:.1f}%"
        sr_ci = f"[{item.get('safe_review_ci_lower', 0.0) * 100:.1f}%, {item.get('safe_review_ci_upper', 0.0) * 100:.1f}%]"

        verdict_name = "TRUSTWORTHY" if item["passed"] else "NOT TRUSTWORTHY"
        if item.get("is_legacy"):
            label = f"Local `{m_name}`*"
            detail = "Did not pass calibration"
            verdict_text = f"**{verdict_name}** ({detail})"
            sr_str = "n/a (not measured)"
        else:
            label = f"Groq `{m_name}`"
            detail = "Passed calibration" if item["passed"] else "Did not pass calibration"
            verdict_text = f"**{verdict_name}** ({detail})"
            sr_str = f"**{sr_pct}** ({sr_cnt}/{sr_tot}) {sr_ci}"

        lines.append(f"| {status} | {label} | **{leak_pct}** {leak_ci} | **{fa_pct}** {fa_ci} | {sr_str} | {verdict_text} |")

    lines.append("")
    lines.append("With `--on-review fail` (default), cases sent to review fail CI; use `--on-review warn` to report them without blocking.")
    lines.append("")
    lines.append("*\\*Evaluated in commit 101a81e on local CPU. Legacy results; see docs/real-model-results.md for raw details.*")
    lines.append("*Calibration uses 50 cases (20 holdout, 8 holdout leaks); treat results as indicative, not a guarantee. Re-run `calibrate` on your own judge and, ideally, your own labelled cases.*")
    return "\n".join(lines)


def replace_between_markers(content: str, begin_marker: str, end_marker: str, new_inner: str) -> str:
    """Safely replace content between comment markers."""
    pattern = re.compile(rf"({re.escape(begin_marker)}\r?\n)(.*?)(\r?\n{re.escape(end_marker)})", re.DOTALL)
    if not pattern.search(content):
        # Try matching even if markers are on consecutive lines
        pattern_empty = re.compile(rf"({re.escape(begin_marker)}\r?\n)({re.escape(end_marker)})")
        if pattern_empty.search(content):
            return pattern_empty.sub(rf"\g<1>{new_inner}\n\g<2>", content)
        raise ValueError(f"Markers {begin_marker} ... {end_marker} not found in content.")
    return pattern.sub(rf"\g<1>{new_inner}\g<3>", content)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and verify benchmark results.")
    parser.add_argument("--check", action="store_true", help="Check that committed files match generated results without modifying disk.")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    raw_dir = repo_root / "docs" / "data" / "raw"
    legacy_file = repo_root / "docs" / "data" / "legacy_results.json"
    judge_cal_file = repo_root / "docs" / "data" / "judge_calibration.json"
    real_results_file = repo_root / "docs" / "real-model-results.md"
    readme_file = repo_root / "README.md"
    chart_svg_file = repo_root / "assets" / "judge-calibration.svg"

    raw_reports = validate_raw_reports(raw_dir)
    legacy_data = validate_legacy_results(legacy_file)
    judge_cal_data = build_judge_calibration_data(raw_reports, legacy_data)

    target_judge_cal_json = json.dumps(judge_cal_data, indent=2) + "\n"
    target_results_table = generate_results_markdown_table(raw_reports, legacy_data)
    target_readme_table = generate_readme_markdown_table(judge_cal_data)

    current_real_results = real_results_file.read_text(encoding="utf-8")
    new_real_results = replace_between_markers(current_real_results, BEGIN_MARKER, END_MARKER, target_results_table)

    current_readme = readme_file.read_text(encoding="utf-8")
    new_readme = replace_between_markers(current_readme, BEGIN_MARKER, END_MARKER, target_readme_table)

    if args.check:
        errors = []
        if not judge_cal_file.exists() or judge_cal_file.read_text(encoding="utf-8") != target_judge_cal_json:
            errors.append(f"{judge_cal_file} differs from generated data.")
        if current_real_results != new_real_results:
            errors.append(f"{real_results_file} generated section differs.")
        if current_readme != new_readme:
            errors.append(f"{readme_file} generated section differs.")
        if errors:
            print("ERROR: Benchmark results out of sync with raw data:", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
            sys.exit(1)
        print("OK: All benchmark tables and data match raw reports and legacy archive.")
        sys.exit(0)

    # Write files
    judge_cal_file.write_text(target_judge_cal_json, encoding="utf-8")
    real_results_file.write_text(new_real_results, encoding="utf-8")
    readme_file.write_text(new_readme, encoding="utf-8")
    generate_judge_calibration_svg(judge_cal_file, chart_svg_file)
    print("Successfully built docs/data/judge_calibration.json, updated markdown tables, and regenerated chart SVG.")


if __name__ == "__main__":
    main()
