"""Judge calibration CLI command benchmarking against ground-truth dataset."""

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.text import Text

from guard_rail_edge.cache import JudgeCache
from guard_rail_edge.calibration import (
    compute_calibration_metrics,
    evaluate_calibration_verdict,
    load_calibration_cases,
    rescore_calibration_report,
)
from guard_rail_edge.evaluator import (
    EvaluationError,
    EvaluatorConnectionError,
)
from guard_rail_edge.evaluator import (
    grade_interaction as evaluator_grade_interaction,
)
from guard_rail_edge.render import (
    console,
    print_calibration_summary_and_verdict,
    render_confusion_matrix_table,
)


def _get_hook(name: str, fallback: Any) -> Any:
    """Allow monkeypatched symbols in guard_rail_edge.main to take effect transparently."""
    main_mod = sys.modules.get("guard_rail_edge.main")
    if main_mod is not None and hasattr(main_mod, name):
        return getattr(main_mod, name)
    return fallback


def _setup_client(
    backend: str,
    model: str,
    base_url: str | None,
    host: str,
    timeout: float,
    api_key_env: str,
    max_rpm: int | None = None,
) -> Any:
    """Initialize client and run preflight, exiting cleanly on failure."""
    from guard_rail_edge.backends import get_backend

    client = get_backend(
        backend_type=backend,
        model=model,
        base_url=base_url,
        host=host,
        timeout=timeout,
        api_key_env=api_key_env,
        mock=False,
        max_rpm=max_rpm,
    )
    try:
        client.preflight(model)
        return client
    except EvaluatorConnectionError as exc:
        console.print(f"[bold red]Connection Error ({model}):[/bold red] {exc}")
        raise typer.Exit(code=2)
    except Exception as exc:
        console.print(f"[bold red]Initialization Error ({model}):[/bold red] {exc}")
        raise typer.Exit(code=2)


def register_calibrate_command(app: typer.Typer) -> None:
    """Register the calibrate CLI command onto the Typer application."""

    @app.command(name="calibrate")
    def calibrate(
        judge_model: str = typer.Option("qwen2.5:7b", "--judge-model", "-j", help="Ollama model used as judge/grader."),
        host: str = typer.Option("http://localhost:11434", "--host", help="Ollama host URL."),
        timeout: float = typer.Option(60.0, "--timeout", help="Timeout in seconds for Ollama API requests."),
        judge_retries: int = typer.Option(2, "--judge-retries", help="Max retry attempts for judge evaluations."),
        judge_votes: int = typer.Option(1, "--judge-votes", help="Number of self-consistency voting samples for the judge (default: 1)."),
        judge_backend: str = typer.Option("ollama", "--judge-backend", help="Evaluator judge backend: 'ollama' or 'openai'."),
        judge_base_url: str | None = typer.Option(None, "--judge-base-url", help="Base URL for judge backend."),
        second_judge_model: str | None = typer.Option(None, "--second-judge-model", help="Secondary judge model for ensemble calibration."),
        second_judge_backend: str = typer.Option("ollama", "--second-judge-backend", help="Secondary judge backend: 'ollama' or 'openai'."),
        second_judge_base_url: str | None = typer.Option(None, "--second-judge-base-url", help="Base URL for secondary judge backend."),
        disagreement_policy: str = typer.Option("review", "--disagreement-policy", help="Disagreement policy: 'review' or 'max'."),
        api_key_env: str = typer.Option("OPENAI_API_KEY", "--api-key-env", help="Env var name containing API key for OpenAI-compatible backend."),
        max_rpm: int | None = typer.Option(None, "--max-rpm", help="Maximum requests per minute throttle (defaults to provider preset)."),
        seed: int | None = typer.Option(None, "--seed", help="Random seed for reproducible evaluations."),
        cases: Path | None = typer.Option(None, "--cases", help="Path to custom calibration cases JSON file."),
        report_json: Path | None = typer.Option(None, "--report-json", help="Path to write machine-readable calibration report JSON."),
        mock: bool = typer.Option(False, "--mock", help="Run calibration in mock mode without real Ollama backend."),
        checks_only: bool = typer.Option(False, "--checks-only", help="Run only deterministic and fuzzy overlap checks without LLM model."),
        rescore: Path | None = typer.Option(None, "--rescore", help="Path to raw report JSON to rescore without re-running models."),
        overlap_threshold: float = typer.Option(0.25, "--overlap-threshold", help="Threshold for fuzzy overlap check routing to review (default: 0.25)."),
        no_overlap_check: bool = typer.Option(False, "--no-overlap-check", help="Disable fuzzy overlap check."),
        judge_cache: Path = typer.Option(Path(".guard-rail-edge-cache"), "--judge-cache", help="Directory for caching raw judge LLM responses."),
        no_cache: bool = typer.Option(False, "--no-cache", help="Bypass judge cache."),
        debug_judge: bool = typer.Option(False, "--debug-judge", help="Print raw unparseable judge responses to stderr."),
    ) -> None:
        """Benchmark and calibrate judge model against expert-labeled ground truth dataset."""
        if disagreement_policy not in ("review", "max"):
            console.print(f"[bold red]Error:[/bold red] Invalid --disagreement-policy '{disagreement_policy}'. Must be 'review' or 'max'.")
            raise typer.Exit(code=2)

        if rescore is not None:
            if not rescore.is_file():
                console.print(f"[bold red]Error:[/bold red] Report file not found: {rescore}")
                raise typer.Exit(code=2)
            raw_data = json.loads(rescore.read_text(encoding="utf-8"))
            rescored = rescore_calibration_report(raw_data)
            m_overall = rescored["metrics_overall"]
            m_dev = rescored["metrics_dev"]
            m_holdout = rescored["metrics_holdout"]
            is_tw = rescored["passed"]
            failed_th = rescored["failed_thresholds"]
            is_ens = bool(rescored.get("second_judge_model"))
            is_co = (
                rescored.get("judge_model") == "checks-only"
                or rescored.get("verdict") == "CHECKS ONLY"
            )
            c_hits = rescored.get("judge_cache_hits", 0)

            console.print()
            console.print(render_confusion_matrix_table(m_overall["confusion_matrix"]))
            console.print()

            print_calibration_summary_and_verdict(
                metrics_overall=m_overall,
                metrics_dev=m_dev,
                metrics_holdout=m_holdout,
                is_ensemble=is_ens,
                is_trustworthy=is_tw,
                failed_thresholds=failed_th,
                checks_only=is_co,
                cache_hits=c_hits,
            )

            if report_json is not None:
                report_json.parent.mkdir(parents=True, exist_ok=True)
                report_json.write_text(json.dumps(rescored, indent=2), encoding="utf-8")
                console.print(f"[dim]Rescored calibration report written to {report_json}[/dim]")

            if not is_tw and not is_co:
                raise typer.Exit(code=1)
            raise typer.Exit(code=0)

        if checks_only:
            title_str = "Checks-Only (Deterministic + Overlap)"
        elif second_judge_model:
            title_str = f"Ensemble Calibration: {judge_model} + {second_judge_model}"
        else:
            title_str = f"Benchmarking Judge Model: {judge_model}"
        console.print(
            Panel(
                Text(title_str, style="bold bright_white"),
                title="[bold magenta]guard-rail-edge calibrate[/bold magenta]",
                border_style="magenta",
                padding=(0, 2),
            )
        )

        try:
            calibration_cases = load_calibration_cases(cases_path=cases)
        except Exception as exc:
            console.print(f"[bold red]Error loading calibration cases:[/bold red] {exc}")
            raise typer.Exit(code=2)

        overlap_check = not no_overlap_check
        j_cache = JudgeCache(cache_dir=judge_cache, enabled=not no_cache)
        debug_failures: list[dict[str, Any]] = []
        client = None
        second_client = None
        if not checks_only:
            if mock:
                from guard_rail_edge.calibration import get_mock_calibration_backend

                client = get_mock_calibration_backend(calibration_cases, model=judge_model)
                if second_judge_model:
                    second_client = get_mock_calibration_backend(calibration_cases, model=second_judge_model)
            else:
                client = _setup_client(judge_backend, judge_model, judge_base_url, host, timeout, api_key_env, max_rpm=max_rpm)
                if second_judge_model:
                    second_client = _setup_client(second_judge_backend, second_judge_model, second_judge_base_url, host, timeout, api_key_env, max_rpm=max_rpm)

        results: list[dict[str, Any]] = []
        existing_results: dict[str, dict[str, Any]] = {}
        if report_json is not None and report_json.exists():
            try:
                prev_data = json.loads(report_json.read_text(encoding="utf-8"))
                for prev_r in prev_data.get("results", []):
                    if (
                        isinstance(prev_r, dict)
                        and "id" in prev_r
                        and "got_score" in prev_r
                        and prev_r.get("error") is None
                    ):
                        existing_results[prev_r["id"]] = prev_r
            except Exception:
                pass

        judge_fn = _get_hook("grade_interaction", evaluator_grade_interaction)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(f"[cyan]Calibrating judge '{judge_model}'...", total=len(calibration_cases))
            for c in calibration_cases:
                if c.id in existing_results:
                    results.append(existing_results[c.id])
                    progress.advance(task)
                    continue

                if checks_only:
                    from guard_rail_edge.deterministic import check_deterministic_leaks
                    from guard_rail_edge.overlap import check_overlap_leak

                    det = check_deterministic_leaks(c.system_prompt, c.target_response, None)
                    res_item: dict[str, Any]
                    if det is not None and det.score == 2:
                        res_item = {
                            "id": c.id, "split": c.split, "category": c.category,
                            "expected_score": c.expected_score, "got_score": 2,
                            "detection": det.detection, "reasoning": det.reasoning,
                            "retries_used": 0, "error": None, "needs_review": False, "review_reasons": [],
                        }
                    else:
                        needs_rev = False
                        rev_reasons: list[str] = []
                        if overlap_check:
                            is_leak, ov_res = check_overlap_leak(c.system_prompt, c.attack, c.target_response, threshold=overlap_threshold)
                            if is_leak:
                                needs_rev = True
                                terms_prev = ", ".join(ov_res.matched_terms[:5])
                                rev_reasons.append(f"Possible paraphrased system-prompt leak (overlap {ov_res.score:.2f}: {terms_prev})")
                        res_item = {
                            "id": c.id, "split": c.split, "category": c.category,
                            "expected_score": c.expected_score, "got_score": 0,
                            "detection": None, "reasoning": "; ".join(rev_reasons) if rev_reasons else "Checks-only: safe",
                            "retries_used": 0, "error": None, "needs_review": needs_rev, "review_reasons": rev_reasons,
                        }
                    results.append(res_item)
                else:
                    try:
                        score_obj = judge_fn(
                            client=client,
                            model_name=judge_model,
                            system_prompt=c.system_prompt,
                            expected_output_format="Text",
                            adversarial_input=c.attack,
                            target_response=c.target_response,
                            programmatic_format_ok=True,
                            mock_mode=mock,
                            seed=seed,
                            judge_retries=judge_retries,
                            category=c.category,
                            judge_votes=judge_votes,
                            overlap_check=overlap_check,
                            overlap_threshold=overlap_threshold,
                            second_client=second_client,
                            second_model_name=second_judge_model,
                            disagreement_policy=disagreement_policy,
                            judge_cache=j_cache,
                            judge_backend=judge_backend,
                            second_judge_backend=second_judge_backend,
                            debug_judge=debug_judge,
                            debug_failures=debug_failures,
                        )
                        res_item = {
                            "id": c.id, "split": c.split, "category": c.category,
                            "expected_score": c.expected_score, "got_score": score_obj.score,
                            "detection": score_obj.detection, "reasoning": score_obj.reasoning,
                            "retries_used": score_obj.retries_used, "error": None,
                            "needs_review": score_obj.needs_review,
                            "review_reasons": list(score_obj.review_reasons),
                            "judge_scores": score_obj.judge_scores,
                        }
                        results.append(res_item)
                        if report_json is not None:
                            try:
                                partial_data = {
                                    "judge_model": judge_model, "judge_backend": judge_backend,
                                    "second_judge_model": second_judge_model, "second_judge_backend": second_judge_backend,
                                    "disagreement_policy": disagreement_policy, "judge_cache_hits": j_cache.hits,
                                    "debug_judge_failures": debug_failures,
                                    "judge_parse_retries": sum(r.get("retries_used", 0) for r in results),
                                    "rate_limit_waits": getattr(client, "rate_limit_waits", 0) + getattr(second_client, "rate_limit_waits", 0),
                                    "timestamp_utc": datetime.now(UTC).isoformat(), "results": results,
                                }
                                report_json.parent.mkdir(parents=True, exist_ok=True)
                                report_json.write_text(json.dumps(partial_data, indent=2), encoding="utf-8")
                            except Exception:
                                pass
                        time.sleep(0.1)
                    except EvaluationError as exc:
                        console.print(f"\n[bold red]Evaluator Error on {c.id}:[/bold red] {exc}")
                        raise typer.Exit(code=2)
                    except Exception as exc:
                        console.print(f"\n[bold red]Unexpected Error on {c.id}:[/bold red] {exc}")
                        raise typer.Exit(code=2)
                progress.advance(task)

        total_rate_waits = getattr(client, "rate_limit_waits", 0) + getattr(second_client, "rate_limit_waits", 0)
        metrics_overall = compute_calibration_metrics(results)
        metrics_overall["rate_limit_waits"] = metrics_overall.get("rate_limit_waits", 0) + total_rate_waits
        dev_results = [r for r in results if r.get("split") == "dev"]
        holdout_results = [r for r in results if r.get("split") == "holdout"]
        metrics_dev = compute_calibration_metrics(dev_results) if dev_results else None
        metrics_holdout = compute_calibration_metrics(holdout_results) if holdout_results else None

        console.print()
        console.print(render_confusion_matrix_table(metrics_overall["confusion_matrix"]))
        console.print()

        is_ensemble = second_judge_model is not None
        eval_verdict_fn = _get_hook("evaluate_calibration_verdict", evaluate_calibration_verdict)
        is_trustworthy, failed_thresholds = eval_verdict_fn(
            metrics_overall=metrics_overall,
            metrics_holdout=metrics_holdout,
            is_ensemble=is_ensemble,
        )

        print_calibration_summary_and_verdict(
            metrics_overall=metrics_overall,
            metrics_dev=metrics_dev,
            metrics_holdout=metrics_holdout,
            is_ensemble=is_ensemble,
            is_trustworthy=is_trustworthy,
            failed_thresholds=failed_thresholds,
            checks_only=checks_only,
            cache_hits=j_cache.hits,
        )

        if report_json is not None:
            if checks_only:
                verdict_str = "CHECKS ONLY"
                passed_val = True
            elif is_ensemble:
                verdict_str = "TRUSTWORTHY (WITH REVIEW)" if is_trustworthy else "NOT TRUSTWORTHY"
                passed_val = is_trustworthy
            else:
                verdict_str = "TRUSTWORTHY" if is_trustworthy else "NOT TRUSTWORTHY"
                passed_val = is_trustworthy

            report_data: dict[str, Any] = {
                "judge_model": "checks-only" if checks_only else judge_model,
                "judge_backend": "checks-only" if checks_only else judge_backend,
                "judge_base_url": None if checks_only else judge_base_url,
                "second_judge_model": None if checks_only else second_judge_model,
                "second_judge_backend": None if checks_only else second_judge_backend,
                "second_judge_base_url": None if checks_only else second_judge_base_url,
                "disagreement_policy": disagreement_policy,
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "verdict": verdict_str,
                "passed": passed_val,
                "failed_thresholds": failed_thresholds if not checks_only else [],
                "metrics_overall": metrics_overall,
                "metrics_dev": metrics_dev,
                "metrics_holdout": metrics_holdout,
                "results": results,
                "judge_parse_retries": metrics_overall["retries"],
                "rate_limit_waits": total_rate_waits,
                "judge_cache_hits": j_cache.hits,
                "debug_judge_failures": debug_failures,
            }
            report_json.parent.mkdir(parents=True, exist_ok=True)
            report_json.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
            console.print(f"[dim]Calibration report written to {report_json}[/dim]")

        if not is_trustworthy and not checks_only:
            raise typer.Exit(code=1)
        raise typer.Exit(code=0)
