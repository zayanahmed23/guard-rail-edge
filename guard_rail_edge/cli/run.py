"""Adversarial evaluation run CLI command."""

import sys
from pathlib import Path

import typer
from rich.panel import Panel
from rich.text import Text

from guard_rail_edge.cli.helpers import (
    assemble_final_tests,
    setup_evaluation_clients,
    version_callback,
)
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
        suite: Path = typer.Option(
            Path("tests.json"),
            "--suite",
            "-s",
            help="Path to the JSON test suite file.",
        ),
        model: str = typer.Option(
            "gemma:2b",
            "--model",
            "-m",
            help="Local Ollama model to use for target simulation.",
        ),
        judge_model: str | None = typer.Option(
            None,
            "--judge-model",
            help="Ollama model to use as evaluator judge (defaults to --model).",
        ),
        patch_model: str | None = typer.Option(
            None,
            "--patch-model",
            help="Ollama model to use for self-healing patch synthesis (defaults to --judge-model).",
        ),
        target_backend: str = typer.Option(
            "ollama",
            "--target-backend",
            help="Target simulation backend: 'ollama' or 'openai'.",
        ),
        target_base_url: str | None = typer.Option(
            None,
            "--target-base-url",
            help="Base URL for target backend (defaults to --host for ollama, or https://api.openai.com/v1 for openai).",
        ),
        judge_backend: str = typer.Option(
            "ollama",
            "--judge-backend",
            help="Evaluator judge backend: 'ollama' or 'openai'.",
        ),
        judge_base_url: str | None = typer.Option(
            None,
            "--judge-base-url",
            help="Base URL for judge backend (defaults to --host for ollama, or https://api.openai.com/v1 for openai).",
        ),
        api_key_env: str = typer.Option(
            "OPENAI_API_KEY",
            "--api-key-env",
            help="Environment variable name containing API key for OpenAI-compatible backend.",
        ),
        host: str = typer.Option(
            "http://localhost:11434",
            "--host",
            help="Ollama server host URL.",
        ),
        timeout: float = typer.Option(
            120.0,
            "--timeout",
            help="Timeout in seconds for Ollama API requests.",
        ),
        judge_retries: int = typer.Option(
            2,
            "--judge-retries",
            min=0,
            help="Number of retries for the judge model on unparseable responses or errors.",
        ),
        judge_votes: int = typer.Option(
            1,
            "--judge-votes",
            help="Number of self-consistency voting samples for the judge (default: 1).",
        ),
        repeats: int = typer.Option(
            1,
            "--repeats",
            min=1,
            help="Number of times to repeat each test (final score is max across runs).",
        ),
        seed: int | None = typer.Option(
            None,
            "--seed",
            help="Deterministic random seed passed to Ollama options.",
        ),
        auto_patch: bool = typer.Option(
            False,
            "--auto-patch",
            "-p",
            help="Enable automated self-healing prompt rewrite if vulnerabilities are detected.",
        ),
        apply: bool = typer.Option(
            False,
            "--apply",
            help="Automatically apply the hardened system prompt directly to the suite file.",
        ),
        force_apply: bool = typer.Option(
            False,
            "--force-apply",
            help="Force applying the hardened prompt even if verification fails or is skipped.",
        ),
        patch_output: Path | None = typer.Option(
            None,
            "--patch-output",
            "-o",
            help="Custom output filepath for generated .patch file (defaults to <suite.stem>.patch).",
        ),
        verify_patch: bool = typer.Option(
            True,
            "--verify-patch/--no-verify-patch",
            help="Re-run failed adversarial tests against the hardened prompt to verify the fix.",
        ),
        fail_on_suspicious: bool = typer.Option(
            False,
            "--fail-on-suspicious",
            help="Exit with code 1 on score >= 1 instead of only score == 2.",
        ),
        fail_on_format: bool = typer.Option(
            False,
            "--fail-on-format",
            help="Fail pipeline (exit 1) if any test response violates output format constraints.",
        ),
        judge_always: bool = typer.Option(
            False,
            "--judge-always",
            help="Run judge even when deterministic checks (markers, regex, canary) detect violations.",
        ),
        pack: list[str] | None = typer.Option(
            None,
            "--pack",
            help="Built-in attack pack to include (repeatable or 'all').",
        ),
        exclude: list[str] | None = typer.Option(
            None,
            "--exclude",
            help="Attack ID to exclude (repeatable).",
        ),
        min_severity: str | None = typer.Option(
            None,
            "--min-severity",
            help="Minimum attack severity to include: low, medium, or high.",
        ),
        report_json: Path | None = typer.Option(
            None,
            "--report-json",
            "-r",
            help="Export a machine-readable JSON security report for CI/CD artifacts.",
        ),
        redact_responses: bool = typer.Option(
            False,
            "--redact-responses",
            help="Redact target responses in the JSON report to first 80 chars + '...[redacted]'.",
        ),
        mock: bool = typer.Option(
            False,
            "--mock",
            help="Run in mock/offline mode with simulated edge responses.",
        ),
        version: bool | None = typer.Option(
            None,
            "--version",
            "-v",
            help="Show guard-rail-edge version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ) -> None:
        """Run automated prompt injection tests against target LLM system prompts."""
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
                "Use --judge-model with a calibrated TRUSTWORTHY model (recommended: qwen2.5:7b)."
            )

        console.print(f"[bold green][OK][/bold green] Ingested test suite from: [cyan]{suite}[/cyan]")
        console.print(f"[dim]Expected Format:[/dim] [bold]{test_suite.expected_output_format}[/bold]")
        console.print(f"[dim]Target Model:[/dim] [bold]{model}[/bold]")
        console.print(f"[dim]Judge Model:[/dim] [bold]{actual_judge_model}[/bold]")
        console.print(f"[dim]Patch Model:[/dim] [bold]{actual_patch_model}[/bold] (Host: {host})")
        console.print(f"[dim]Auto-Patch Mode:[/dim] [bold]{'Enabled' if (auto_patch or apply) else 'Disabled'}[/bold]")
        console.print(f"[dim]Apply In-Place:[/dim] [bold]{'Enabled' if apply else 'Disabled'}[/bold]")
        console.print(f"[dim]Fail-on-Suspicious:[/dim] [bold]{fail_on_suspicious}[/bold]\n")

        # 3. Pre-flight health check
        target_client, judge_client, patch_client = setup_evaluation_clients(
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
        )

        # 4. Evaluation
        test_results, total_judge_retries = evaluate_suite(
            target_client=target_client,
            judge_client=judge_client,
            model=model,
            judge_model=actual_judge_model,
            system_prompt=test_suite.system_prompt or "",
            expected_output_format=test_suite.expected_output_format,
            tests=final_tests,
            canary=test_suite.canary,
            required_json_keys=test_suite.required_json_keys,
            mock=mock,
            repeats=repeats,
            seed=seed,
            judge_retries=judge_retries,
            judge_always=judge_always,
            judge_votes=judge_votes,
        )

        # 5. Summarize
        (
            safe_count,
            suspicious_count,
            jailbroken_count,
            format_failure_count,
            error_count,
            pipeline_passed,
            failed_tests,
        ) = summarize(
            test_results,
            fail_on_suspicious=fail_on_suspicious,
            fail_on_format=fail_on_format,
            mock=mock,
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
            )

        # 10. Exit code contract
        if applied_verified_prompt:
            console.print("[bold green]CI/CD Guardrail Passed: Hardened prompt verified and applied successfully.[/bold green]")
            sys.exit(0)

        if error_count > 0:
            console.print("[bold magenta]CI/CD Evaluation Failed: Infrastructure or evaluator errors occurred.[/bold magenta]")
            sys.exit(2)

        if not pipeline_passed:
            console.print("[bold red]CI/CD Guardrail Check Failed: Pipeline blocked until the proposed patch is reviewed and applied.[/bold red]")
            sys.exit(1)

        console.print("[bold green]CI/CD Guardrail Passed: All adversarial prompts handled safely.[/bold green]")
        sys.exit(0)
