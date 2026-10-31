"""Format Guard-Rail-Edge JSON report into GitHub Actions Step Summary Markdown."""

import argparse
import json
import sys
from pathlib import Path


def format_step_summary(report_path: Path, exit_code: int) -> str:
    """Read EvaluationReport JSON and render GitHub step summary Markdown."""
    lines: list[str] = ["## 🛡️ Guard-Rail-Edge Security Gate Evaluation", ""]

    if not report_path.is_file():
        lines.append(f"> ⚠️ **VERDICT: ERROR** (Exit {exit_code}) — Report file `{report_path}` not found.")
        return "\n".join(lines)

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        lines.append(f"> ⚠️ **VERDICT: ERROR** (Exit {exit_code}) — Could not parse report JSON: {exc}")
        return "\n".join(lines)

    passed = report.get("pipeline_passed", False)
    total_tests = report.get("total_tests", 0)
    safe_cnt = report.get("safe_count", 0)
    susp_cnt = report.get("suspicious_count", 0)
    jail_cnt = report.get("jailbroken_count", 0)
    review_cnt = report.get("needs_review_count", 0)
    err_cnt = report.get("error_count", 0)
    fmt_cnt = report.get("format_failure_count", 0)
    patch_path = report.get("patch_generated")

    # 1. Verdict Banner
    if exit_code == 0 and passed:
        lines.append("> 🟢 **VERDICT: PASSED** — All evaluated test cases passed security thresholds.")
    elif exit_code == 3 or (not passed and review_cnt > 0 and jail_cnt == 0 and susp_cnt == 0):
        lines.append("> 🟡 **VERDICT: NEEDS REVIEW** (Exit 3) — Evaluation produced uncertain signals or judge disagreement.")
    elif exit_code == 1 or not passed:
        lines.append(f"> 🔴 **VERDICT: BLOCKED** (Exit {exit_code}) — Vulnerability or prompt leakage detected.")
    else:
        lines.append(f"> ⚠️ **VERDICT: RUNTIME ERROR** (Exit {exit_code}) — An operational error occurred during evaluation.")

    lines.append("")

    # 2. Key Metrics Table
    lines.append("### 📊 Evaluation Metrics")
    lines.append("| Metric | Count | Details |")
    lines.append("|---|:---:|---|")
    lines.append(f"| **Total Tests** | **{total_tests}** | Suite: `{report.get('suite_path', 'unknown')}` |")
    lines.append(f"| Safe (0) | {safe_cnt} | Compliant responses |")
    lines.append(f"| Suspicious (1) | {susp_cnt} | Partial leakage or boundary evasion |")
    lines.append(f"| Jailbroken (2) | {jail_cnt} | Full prompt exfiltration or instruction override |")
    lines.append(f"| Needs Review | {review_cnt} | Overlap threshold or judge disagreement |")
    if fmt_cnt > 0:
        lines.append(f"| Format Failures | {fmt_cnt} | Violated expected output schema |")
    if err_cnt > 0:
        lines.append(f"| Execution Errors | {err_cnt} | Engine or network timeouts |")
    lines.append("")

    # 3. Security Findings Table (if any non-safe cases)
    results = report.get("results", [])
    findings = [r for r in results if r.get("got_score", 0) > 0 or r.get("needs_review") or r.get("error")]
    if findings:
        lines.append("### 🚨 Detected Security Findings")
        lines.append("| Test Scenario | Category | Score | Detection | Reason / Notes |")
        lines.append("|---|---|:---:|:---:|---|")
        for f in findings:
            name = f.get("name", "Unknown test")
            cat = f.get("category", "custom")
            score = f.get("got_score", 0)
            det = f.get("detection") or ("AUTO-CANARY" if "canary" in str(f.get("reasoning", "")).lower() else "JUDGE")
            reason = f.get("reasoning", "") or ""
            # Clean up reasoning to single line
            reason = reason.replace("\n", " ").strip()
            if len(reason) > 120:
                reason = reason[:117] + "..."
            score_badge = f"**{score}**"
            if f.get("needs_review"):
                score_badge += " (Review)"
            lines.append(f"| `{name}` | {cat} | {score_badge} | {det} | {reason} |")
        lines.append("")

    # 4. Auto-Patch proposal if present
    if patch_path:
        lines.append("### 🩹 Automated Self-Healing Patch")
        lines.append(f"A hardened system prompt patch was synthesized and saved to `{patch_path}`.")
        lines.append("Review and apply it locally with `git apply <patch_file>` or re-run with `--apply`.")
        lines.append("")

    # 5. Docs Link
    lines.append("---")
    lines.append("*Exit code reference & configuration guide: [guard-rail-edge Documentation](https://github.com/zayanahmed23/guard-rail-edge#cicd-pipeline-integration)*")
    return "\n".join(lines)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Format Guard-Rail-Edge report for GitHub Step Summary.")
    parser.add_argument("--report", required=True, type=Path, help="Path to evaluation report JSON.")
    parser.add_argument("--exit-code", default=0, type=int, help="Exit code of guard-rail-edge run.")
    parser.add_argument("--output", type=Path, default=None, help="Filepath to append summary Markdown to.")
    args = parser.parse_args()

    summary_md = format_step_summary(args.report, args.exit_code)
    if args.output:
        with open(args.output, "a", encoding="utf-8") as f:
            f.write(summary_md + "\n")
    else:
        try:
            print(summary_md)
        except UnicodeEncodeError:
            sys.stdout.buffer.write((summary_md + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
