import hashlib
import sys
from pathlib import Path
from typing import Any

import typer
from rich.panel import Panel
from rich.text import Text

from guard_rail_edge.cache import JudgeCache
from guard_rail_edge.cli.helpers import (
    assemble_final_tests,
    setup_evaluation_clients,
    version_callback,
)
from guard_rail_edge.deterministic import generate_auto_canary
from guard_rail_edge.render import console
from guard_rail_edge.report import write_report
from guard_rail_edge.runner import (
    evaluate_suite,
    heal,
    load_suite,
    summarize,
)
from guard_rail_edge.schemas import (
    HardenedPromptProposal,
    VerificationResult,
)
from guard_rail_edge.verification import (
    apply_hardened_prompt_to_disk,
    run_post_patch_verification,
)


def register_run_command(app: typer.Typer) -> None:
    """Register the run CLI command onto the Typer application."""

    @app.command()
    def run(
        suite: Path = typer.Option(Path("tests.json"), "--suite", "-s", help="Path to the JSON test suite file."),
        model: str = typer.Option("gemma:2b", "--model", "-m", help="Local Ollama model for target simulation."),
        judge_model: str | None = typer.Option(None, "--judge-model", help="Evaluator judge model (defaults to --model)."),
        patch_model: str | None = typer.Option(None, "--patch-model", help="Model for patch synthesis (defaults to --judge-model)."),
        target_backend: str = typer.Option("ollama", "--target-backend", help="Target backend: 'ollama' or 'openai'."),
        target_base_url: str | None = typer.Option(None, "--target-base-url", help="Base URL for target backend."),
        judge_backend: str = typer.Option("ollama", "--judge-backend", help="Judge backend: 'ollama' or 'openai'."),
        judge_base_url: str | None = typer.Option(None, "--judge-base-url", help="Base URL for judge backend."),
        second_judge_model: str | None = typer.Option(None, "--second-judge-model", help="Second judge model for ensemble cross-checking."),
        second_judge_backend: str = typer.Option("ollama", "--second-judge-backend", help="Second judge backend: 'ollama' or 'openai'."),
        second_judge_base_url: str | None = typer.Option(None, "--second-judge-base-url", help="Base URL for second judge backend."),
        disagreement_policy: str = typer.Option("review", "--disagreement-policy", help="Disagreement policy: 'review' or 'max'."),
        api_key_env: str = typer.Option("OPENAI_API_KEY", "--api-key-env", help="Env var name for OpenAI-compatible API key."),
        host: str = typer.Option("http://localhost:11434", "--host", help="Ollama server host URL."),
        timeout: float = typer.Option(120.0, "--timeout", help="Timeout in seconds for API requests."),
        judge_retries: int = typer.Option(2, "--judge-retries", min=0, help="Max retries for unparseable judge responses."),
        judge_votes: int = typer.Option(1, "--judge-votes", help="Number of self-consistency voting samples for judge."),
        repeats: int = typer.Option(1, "--repeats", min=1, help="Repeat count per test (final score is max)."),
        seed: int | None = typer.Option(None, "--seed", help="Deterministic random seed passed to options."),
        auto_patch: bool = typer.Option(False, "--auto-patch", "-p", help="Enable automated self-healing prompt rewrite."),
        apply: bool = typer.Option(False, "--apply", help="Apply hardened system prompt directly to suite file."),
        force_apply: bool = typer.Option(False, "--force-apply", help="Force applying hardened prompt without verification."),
        patch_output: Path | None = typer.Option(None, "--patch-output", "-o", help="Custom output filepath for .patch file."),
        verify_patch: bool = typer.Option(True, "--verify-patch/--no-verify-patch", help="Re-run tests to verify fix."),
        fail_on_suspicious: bool = typer.Option(False, "--fail-on-suspicious", help="Exit code 1 on score >= 1."),
        fail_on_format: bool = typer.Option(False, "--fail-on-format", help="Fail pipeline if format violated."),
        on_review: str = typer.Option("fail", "--on-review", help="Policy for needs-review: 'fail' or 'warn'."),
        auto_canary: bool = typer.Option(True, "--auto-canary/--no-auto-canary", help="Inject unique per-run canary."),
        judge_always: bool = typer.Option(False, "--judge-always", help="Run judge even when deterministic checks fire."),
        overlap_check: bool = typer.Option(True, "--overlap-check/--no-overlap-check", help="Enable fuzzy overlap leak detection."),
        overlap_threshold: float = typer.Option(0.25, "--overlap-threshold", help="Threshold for fuzzy overlap check."),
        judge_cache: Path | None = typer.Option(None, "--judge-cache", help="Directory for caching raw judge LLM responses."),
        no_cache: bool = typer.Option(False, "--no-cache", help="Bypass judge cache."),
        debug_judge: bool = typer.Option(False, "--debug-judge", help="Print raw unparseable judge responses to stderr."),
        pack: list[str] | None = typer.Option(None, "--pack", help="Built-in attack pack to include (repeatable/all)."),
        exclude: list[str] | None = typer.Option(None, "--exclude", help="Attack ID to exclude (repeatable)."),
        min_severity: str | None = typer.Option(None, "--min-severity", help="Minimum severity: low, medium, or high."),
        report_json: Path | None = typer.Option(None, "--report-json", "-r", help="Export report JSON."),
        redact_responses: bool = typer.Option(False, "--redact-responses", help="Redact target responses in report."),
        mock: bool = typer.Option(False, "--mock", help="Run in mock/offline mode."),
        version: bool | None = typer.Option(None, "--version", "-v", help="Show version and exit.", callback=version_callback, is_eager=True),
    ) -> None:
        """Run automated prompt injection tests against target LLM system prompts."""
        if on_review not in ("fail", "warn"):
            console.print(f"[bold red]Error:[/bold red] Invalid --on-review policy '{on_review}'. Must be 'fail' or 'warn'.")
            sys.exit(2)
        if disagreement_policy not in ("review", "max"):
            console.print(f"[bold red]Error:[/bold red] Invalid --disagreement-policy '{disagreement_policy}'. Must be 'review' or 'max'.")
            sys.exit(2)

        if apply and not verify_patch and not force_apply:
            console.print("[bold red]Error:[/bold red] --apply with --no-verify-patch requires --force-apply to prevent writing unverified prompts.")
            sys.exit(2)

        # 1. Visually distinct header
        if mock:
            header_text = Text("MOCK MODE - SIMULATED RESPONSES, NOT A REAL SECURITY RESULT", style="bold yellow")
            console.print(Panel(header_text, border_style="yellow", padding=(1, 2)))
        else:
            header_text = Text("Starting Guard-Rail Edge Evaluator...", style="bold cyan")
            console.print(Panel(header_text, border_style="cyan", padding=(1, 2)))

        # 2. Ingest and validate JSON test suite & assemble tests
        test_suite, prompt_target_file = load_suite(suite)
        final_tests, all_requested_packs = assemble_final_tests(
            test_suite=test_suite,
            cli_packs=pack,
            cli_excludes=exclude,
            cli_min_severity=min_severity,
        )

        actual_judge_model = judge_model if judge_model is not None else model
        actual_patch_model = patch_model if patch_model is not None else actual_judge_model

        if actual_judge_model == model:
            console.print(
                "[bold yellow]Warning:[/bold yellow] Judge model is the same as the target model; scores may be biased. "
                "Use --judge-model with a stronger, calibrated model."
            )

        console.print(f"[bold green][OK][/bold green] Ingested test suite from: [cyan]{suite}[/cyan]")
        console.print(f"[dim]Expected Format:[/dim] [bold]{test_suite.expected_output_format}[/bold]")
        console.print(f"[dim]Target Model:[/dim] [bold]{model}[/bold]")
        console.print(f"[dim]Judge Model:[/dim] [bold]{actual_judge_model}[/bold]")
        if second_judge_model:
            console.print(f"[dim]Second Judge:[/dim] [bold]{second_judge_model}[/bold] (Backend: {second_judge_backend}, Policy: {disagreement_policy})")
        console.print(f"[dim]Patch Model:[/dim] [bold]{actual_patch_model}[/bold] (Host: {host})")
        console.print(f"[dim]Auto-Patch Mode:[/dim] [bold]{'Enabled' if (auto_patch or apply) else 'Disabled'}[/bold]")
        console.print(f"[dim]Apply In-Place:[/dim] [bold]{'Enabled' if apply else 'Disabled'}[/bold]")
        console.print(f"[dim]Fail-on-Suspicious:[/dim] [bold]{fail_on_suspicious}[/bold]\n")

        # 3. Pre-flight health check
        target_client, judge_client, patch_client, second_judge_client = setup_evaluation_clients(
            target_backend=target_backend,
            judge_backend=judge_backend,
            model=model,
            actual_judge_model=actual_judge_model,
            actual_patch_model=actual_patch_model,
            target_base_url=target_base_url,
            judge_base_url=judge_base_url,
            host=host,
            timeout=timeout,
            api_key_env=api_key_env,
            mock=mock,
            second_judge_backend=second_judge_backend,
            second_judge_model=second_judge_model,
            second_judge_base_url=second_judge_base_url,
        )

        # 4. Evaluation
        per_run_canary = generate_auto_canary() if auto_canary else None
        auto_canary_hash = (
            hashlib.sha256(per_run_canary.encode("utf-8")).hexdigest() if per_run_canary else None
        )
        j_cache = JudgeCache(cache_dir=judge_cache, enabled=(judge_cache is not None and not no_cache))
        debug_failures: list[dict[str, Any]] = []
        test_results, total_judge_retries = evaluate_suite(
            target_client=target_client,
            judge_client=judge_client,
            second_judge_client=second_judge_client,
            second_judge_model=second_judge_model,
            disagreement_policy=disagreement_policy,
            model=model,
            judge_model=actual_judge_model,
            system_prompt=test_suite.system_prompt or "",
            expected_output_format=test_suite.expected_output_format,
            tests=final_tests,
            canary=test_suite.canary,
            auto_canary=per_run_canary,
            required_json_keys=test_suite.required_json_keys,
            mock=mock,
            repeats=repeats,
            seed=seed,
            judge_retries=judge_retries,
            judge_always=judge_always,
            judge_votes=judge_votes,
            overlap_check=overlap_check,
            overlap_threshold=overlap_threshold,
            judge_cache=j_cache,
            judge_backend=judge_backend,
            second_judge_backend=second_judge_backend,
            debug_judge=debug_judge,
            debug_failures=debug_failures,
        )

        # 5. Summarize
        (
            safe_count, suspicious_count, jailbroken_count, needs_review_count,
            format_failure_count, error_count, pipeline_passed, failed_tests,
        ) = summarize(
            test_results,
            fail_on_suspicious=fail_on_suspicious,
            fail_on_format=fail_on_format,
            mock=mock,
            on_review=on_review,
        )

        hardened_proposal: HardenedPromptProposal | None = None
        hardening_source: str | None = None
        saved_patch_path: Path | None = None
        verification_results: list[VerificationResult] | None = None
        applied_verified_prompt: bool = False

        # 6. Heal & Verification
        if not pipeline_passed and (auto_patch or apply) and failed_tests:
            hardened_proposal, hardening_source, diff_text, saved_patch_path = heal(
                client=patch_client,
                patch_model=actual_patch_model,
                suite=suite,
                prompt_target_file=prompt_target_file,
                system_prompt=test_suite.system_prompt or "",
                expected_output_format=test_suite.expected_output_format,
                failed_tests=failed_tests,
                mock=mock,
                patch_output=patch_output,
            )

            # 7. Verification Loop (--verify-patch)
            if verify_patch:
                verification_results, verif_retries = run_post_patch_verification(
                    target_client=target_client,
                    judge_client=judge_client,
                    model=model,
                    actual_judge_model=actual_judge_model,
                    hardened_proposal=hardened_proposal,
                    test_suite=test_suite,
                    final_tests=final_tests,
                    test_results=test_results,
                    fail_on_suspicious=fail_on_suspicious,
                    mock=mock,
                    repeats=repeats,
                    seed=seed,
                    judge_retries=judge_retries,
                    judge_votes=judge_votes,
                    enable_auto_canary=auto_canary,
                )
                total_judge_retries += verif_retries

            # 8. Apply
            if apply:
                has_issues = False
                if verification_results is not None:
                    has_issues = any(
                        v.status in ("STILL VULNERABLE", "REGRESSED") or v.error is not None
                        for v in verification_results
                    )
                if (not has_issues) or force_apply:
                    apply_hardened_prompt_to_disk(
                        suite=suite,
                        prompt_target_file=prompt_target_file,
                        hardened_proposal=hardened_proposal,
                    )
                    if not has_issues:
                        applied_verified_prompt = True
                else:
                    target_desc = "prompt file" if prompt_target_file != suite else "suite file"
                    console.print(f"[bold red]Hardened prompt did not pass verification; {target_desc} NOT modified[/bold red]\n")

            if not apply:
                console.print(
                    f"[dim]To apply this patch to your repo, run: [bold white]git apply {saved_patch_path}[/bold white] "
                    f"or re-run with [bold white]--apply[/bold white][/dim]\n"
                )

        # 9. Machine-Readable CI/CD Report Export (--report-json)
        if report_json is not None:
            write_report(
                report_json=report_json,
                suite=suite,
                model=model,
                judge_model=actual_judge_model,
                patch_model=actual_patch_model,
                test_results=test_results,
                safe_count=safe_count,
                suspicious_count=suspicious_count,
                jailbroken_count=jailbroken_count,
                format_failure_count=format_failure_count,
                error_count=error_count,
                pipeline_passed=pipeline_passed or applied_verified_prompt,
                saved_patch_path=saved_patch_path,
                hardened_proposal=hardened_proposal,
                hardening_source=hardening_source,
                verification_results=verification_results,
                fail_on_suspicious=fail_on_suspicious,
                fail_on_format=fail_on_format,
                mock=mock,
                redact_responses=redact_responses,
                judge_retry_count=total_judge_retries,
                packs=all_requested_packs,
                target_backend=target_backend,
                target_base_url=target_base_url,
                judge_backend=judge_backend,
                judge_base_url=judge_base_url,
                needs_review_count=needs_review_count,
                auto_canary_used=auto_canary,
                auto_canary_hash=auto_canary_hash,
                auto_canary=per_run_canary,
                judge_cache_hits=j_cache.hits,
                debug_judge_failures=debug_failures,
            )

        # 10. Exit code contract (Priority: 2 > 1 > 3 > 0)
        if error_count > 0:
            console.print("[bold magenta]CI/CD Evaluation Failed: Infrastructure or evaluator errors occurred.[/bold magenta]")
            sys.exit(2)

        has_vulnerabilities = (
            jailbroken_count > 0
            or (fail_on_suspicious and suspicious_count > 0)
            or (fail_on_format and format_failure_count > 0)
        )
        if has_vulnerabilities:
            if applied_verified_prompt:
                console.print("[bold green]CI/CD Guardrail Passed: Hardened prompt verified and applied successfully.[/bold green]")
                sys.exit(0)
            console.print("[bold red]CI/CD Guardrail Check Failed: Pipeline blocked until the proposed patch is reviewed and applied.[/bold red]")
            sys.exit(1)

        if on_review == "fail" and needs_review_count > 0:
            if applied_verified_prompt:
                console.print("[bold green]CI/CD Guardrail Passed: Hardened prompt verified and applied successfully.[/bold green]")
                sys.exit(0)
            console.print("[bold yellow]CI/CD Guardrail Needs Review: Pipeline blocked due to unconfirmed items requiring human review.[/bold yellow]")
            sys.exit(3)

        console.print("[bold green]CI/CD Guardrail Passed: All adversarial prompts handled safely.[/bold green]")
        sys.exit(0)
