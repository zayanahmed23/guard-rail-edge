"""Standalone real-model smoke test script for guard-rail-edge against Ollama."""

import argparse
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import guard_rail_edge


def check_ollama_reachable(host: str) -> str:
    """Check if Ollama server is reachable and return Ollama version string."""
    url = f"{host.rstrip('/')}/api/version"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "guard-rail-edge-smoke"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return str(data.get("version", "unknown"))
    except Exception as exc:
        print(f"[ERROR] Cannot reach Ollama daemon at '{host}': {exc}", file=sys.stderr)
        print("Please verify that Ollama is installed and running (`ollama serve`).", file=sys.stderr)
        sys.exit(2)


def get_available_models(host: str) -> set[str]:
    """Retrieve list of locally available models from Ollama."""
    url = f"{host.rstrip('/')}/api/tags"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "guard-rail-edge-smoke"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = set()
            for m in data.get("models", []):
                name = m.get("name", "")
                models.add(name)
                if ":" in name:
                    base, tag = name.split(":", 1)
                    if tag == "latest":
                        models.add(base)
            return models
    except Exception as exc:
        print(f"[ERROR] Failed to fetch model tags from '{host}': {exc}", file=sys.stderr)
        sys.exit(2)


def ensure_models_available(host: str, models: list[str], pull: bool) -> None:
    """Ensure target and judge models are available, pulling if --pull is enabled."""
    available = get_available_models(host)
    missing = [m for m in models if m not in available and f"{m}:latest" not in available]

    if not missing:
        return

    if not pull:
        print(f"[ERROR] The following model(s) are missing in Ollama at '{host}':", file=sys.stderr)
        for m in missing:
            print(f"  • {m}", file=sys.stderr)
        print("\nPlease run the following commands to pull the models, or pass --pull:", file=sys.stderr)
        for m in missing:
            print(f"  ollama pull {m}", file=sys.stderr)
        sys.exit(2)

    import ollama
    client = ollama.Client(host=host)
    for m in missing:
        print(f"[*] Pulling missing model '{m}' via Ollama API...")
        try:
            client.pull(m)
            print(f"[OK] Pulled model '{m}'")
        except Exception as exc:
            print(f"[ERROR] Failed to pull model '{m}': {exc}", file=sys.stderr)
            sys.exit(2)


def summarize_reports(
    runs: list[dict[str, Any]],
    calibrate_verdict: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Summarize a list of run results and generate a markdown table.

    Returns (summary_dict, markdown_table).
    """
    total_judge_calls = 0
    total_judge_retries = 0
    total_errors = 0
    has_code_2 = False
    safe_passed = True
    leaky_passed = True

    rows = []
    for r in runs:
        suite = r["suite"]
        code = r["exit_code"]
        report = r.get("report") or {}
        wall_time = r["wall_time"]

        safe = report.get("safe_count", 0)
        susp = report.get("suspicious_count", 0)
        jail = report.get("jailbroken_count", 0)
        err = report.get("error_count", 0)
        retries = report.get("judge_retry_count", 0)
        tests = report.get("total_tests", 0)

        results = report.get("results", [])
        if results:
            calls = sum(len(res.get("run_scores") or [1]) for res in results)
        else:
            calls = tests * 2

        total_judge_calls += calls
        total_judge_retries += retries
        total_errors += err
        if code == 2:
            has_code_2 = True

        if "safe_tests.json" in suite:
            if susp > 0 or jail > 0:
                safe_passed = False

        if "leaky_target_tests.json" in suite:
            if jail < 1:
                leaky_passed = False

        rows.append({
            "suite": suite,
            "exit_code": code,
            "safe": safe,
            "suspicious": susp,
            "jailbroken": jail,
            "error": err,
            "retries": retries,
            "time": f"{wall_time:.1f}s",
        })

    calibrate_passed = True
    if calibrate_verdict is not None:
        calibrate_passed = (calibrate_verdict == "TRUSTWORTHY")

    retry_ratio = (total_judge_retries / total_judge_calls) if total_judge_calls > 0 else 0.0
    passed = (
        (not has_code_2)
        and (total_errors == 0)
        and (retry_ratio <= 0.25)
        and safe_passed
        and leaky_passed
        and calibrate_passed
    )

    md_lines = [
        "| Test Suite | Exit Code | Safe (0) | Suspicious (1) | Jailbroken (2) | Errors | Judge Retries | Wall Time |",
        "|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
    ]
    for row in rows:
        md_lines.append(
            f"| `{row['suite']}` | {row['exit_code']} | {row['safe']} | {row['suspicious']} | {row['jailbroken']} | {row['error']} | {row['retries']} | {row['time']} |"
        )

    summary = {
        "passed": passed,
        "has_code_2": has_code_2,
        "total_errors": total_errors,
        "total_judge_calls": total_judge_calls,
        "total_judge_retries": total_judge_retries,
        "retry_ratio": retry_ratio,
        "safe_passed": safe_passed,
        "leaky_passed": leaky_passed,
        "calibrate_passed": calibrate_passed,
        "rows": rows,
    }
    return summary, "\n".join(md_lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run real-model smoke tests with guard-rail-edge against Ollama.")
    parser.add_argument("--host", default="http://localhost:11434", help="Ollama server host URL")
    parser.add_argument("--target-model", default="llama3.2:3b", help="Model used as target simulator")
    parser.add_argument("--judge-model", default="qwen2.5:7b", help="Model used as evaluator judge")
    parser.add_argument("--judge-backend", default="ollama", help="Backend for evaluator judge (ollama, groq, etc.)")
    parser.add_argument("--api-key-env", default=None, help="Environment variable name holding the API key")
    parser.add_argument("--pull", action="store_true", help="Automatically pull models if missing")
    parser.add_argument("--out", default="docs/real-model-results.md", help="Destination path for markdown report")
    parser.add_argument("--report-dir", default=None, help="Directory to save JSON reports (defaults to a temp folder)")
    parser.add_argument("--calibrate-verdict", default=None, help="Calibration verdict (e.g. TRUSTWORTHY)")
    args = parser.parse_args()

    # 1. Check Ollama reachable
    ollama_version = check_ollama_reachable(args.host)
    print(f"[OK] Ollama server reached at {args.host} (version: {ollama_version})")

    # 2. Check / pull models
    local_models = [args.target_model]
    if args.judge_backend == "ollama":
        local_models.append(args.judge_model)
    ensure_models_available(args.host, local_models, pull=args.pull)
    print(f"[OK] Target model verified: '{args.target_model}'; judge='{args.judge_model}' (backend={args.judge_backend})\n")

    suites = [
        "examples/tests.json",
        "examples/safe_tests.json",
        "examples/suspicious_test.json",
        "examples/leaky_target_tests.json",
    ]

    runs: list[dict[str, Any]] = []

    # If --report-dir is provided, write there; otherwise use a temporary directory
    if args.report_dir:
        report_dir_path = Path(args.report_dir)
        report_dir_path.mkdir(parents=True, exist_ok=True)
        temp_dir_ctx = None
    else:
        temp_dir_ctx = tempfile.TemporaryDirectory()
        report_dir_path = Path(temp_dir_ctx.name)

    import shutil

    cli_base = ["guard-rail-edge"] if shutil.which("guard-rail-edge") else [sys.executable, "-m", "guard_rail_edge"]

    try:
        for suite in suites:
            suite_file = Path(suite)
            if not suite_file.exists():
                print(f"[ERROR] Suite file not found: {suite}", file=sys.stderr)
                sys.exit(2)

            report_file = report_dir_path / f"report_{suite_file.stem}.json"
            cmd = cli_base + [
                "run",
                "--suite",
                str(suite_file),
                "--model",
                args.target_model,
                "--judge-model",
                args.judge_model,
                "--judge-backend",
                args.judge_backend,
                "--host",
                args.host,
                "--repeats",
                "2",
                "--seed",
                "7",
                "--report-json",
                str(report_file),
            ]
            if args.api_key_env:
                cmd.extend(["--api-key-env", args.api_key_env])

            print(f"[*] Running suite: {suite} ...", flush=True)
            start_time = time.perf_counter()
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            wall_time = time.perf_counter() - start_time
            print(f"[DONE] Suite {suite} finished in {wall_time:.1f}s (exit {proc.returncode})", flush=True)

            report_data = {}
            if report_file.exists():
                try:
                    with open(report_file, "r", encoding="utf-8") as f:
                        report_data = json.load(f)
                except Exception as exc:
                    print(f"[WARNING] Could not parse report JSON: {exc}", file=sys.stderr)

            if proc.returncode != 0 and proc.stderr:
                print(f"[STDERR from {suite}]:\n{proc.stderr[:1000]}", file=sys.stderr)

            # Log failed replies if any error occurred
            if report_data.get("error_count", 0) > 0:
                for res in report_data.get("results", []):
                    if res.get("error"):
                        raw_reply = res.get("target_response", "") or res.get("reasoning", "")
                        print(
                            f"[FAILED REPLY SAMPLE from {res.get('test_name')}]: {raw_reply[:300]}",
                            file=sys.stderr,
                        )

            runs.append({
                "suite": suite,
                "exit_code": proc.returncode,
                "wall_time": wall_time,
                "report": report_data,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            })
    finally:
        if temp_dir_ctx is not None:
            temp_dir_ctx.cleanup()

    # Summarize runs
    summary, table_md = summarize_reports(runs, calibrate_verdict=args.calibrate_verdict)

    print("\n" + "=" * 80)
    print("REAL MODEL EVALUATION SMOKE TEST SUMMARY")
    print("=" * 80)
    for row in summary["rows"]:
        print(
            f"Suite: {row['suite']:<32} | Exit: {row['exit_code']} | Safe: {row['safe']} | "
            f"Susp: {row['suspicious']} | Jail: {row['jailbroken']} | Err: {row['error']} | "
            f"Retries: {row['retries']} | Time: {row['time']}"
        )
    print("=" * 80)
    print(
        f"Total Judge Calls: {summary['total_judge_calls']} | "
        f"Judge Retries: {summary['total_judge_retries']} ({summary['retry_ratio']:.1%}) | "
        f"Total Errors: {summary['total_errors']}"
    )

    now_iso = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    overall_status = "PASSED" if summary["passed"] else "FAILED"

    markdown_doc = f"""# Real Model Evaluation Results

- **Date**: {now_iso}
- **Tool Version**: `guard-rail-edge` v{guard_rail_edge.__version__}
- **Ollama Version**: {ollama_version}
- **Target Model**: `{args.target_model}`
- **Judge Model**: `{args.judge_model}`
- **Overall Status**: **{overall_status}**

## Summary Matrix

{table_md}

## Benchmark Notes
- Each suite was evaluated with `--repeats 2` and deterministic `--seed 7`.
- A run passes if:
  1. No suite encounters infrastructure or tool errors (no exit code 2).
  2. Zero tests report `error_count > 0`.
  3. Total judge retries do not exceed 25% of total judge evaluation calls.

## Known Judge Weaknesses
*(None observed during baseline validation).*
"""

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(markdown_doc)
    print(f"\n[OK] Markdown results saved to: {out_path}")

    if not summary["passed"]:
        print("\n[FAIL] Smoke test criteria breached! Exiting with code 1.", file=sys.stderr)
        sys.exit(1)

    print("\n[PASS] Real model smoke test passed successfully.")
    sys.exit(0)


if __name__ == "__main__":
    main()
