"""Helper functions for attack assembly and backend client setup in CLI run."""

import sys
from typing import Any

import typer
from rich.panel import Panel

from guard_rail_edge.attacks import list_available_packs, load_attacks
from guard_rail_edge.evaluator import EvaluatorConnectionError
from guard_rail_edge.render import console
from guard_rail_edge.runner import preflight
from guard_rail_edge.schemas import AdversarialTest, TestSuite


def version_callback(value: bool) -> None:
    """Print package version and exit."""
    if value:
        import guard_rail_edge

        console.print(f"guard-rail-edge {guard_rail_edge.__version__}")
        raise typer.Exit()


def assemble_final_tests(
    test_suite: TestSuite,
    cli_packs: list[str] | None = None,
    cli_excludes: list[str] | None = None,
    cli_min_severity: str | None = None,
) -> tuple[list[AdversarialTest], list[str]]:
    """Validate attack packs and merge custom suite tests with selected library attacks."""
    available_pack_names = list_available_packs()
    packs_list = list(cli_packs or [])
    all_requested_packs = list(test_suite.packs) + packs_list

    for p in all_requested_packs:
        p_clean = p.strip()
        if p_clean.lower() != "all" and p_clean not in available_pack_names:
            console.print(
                f"[bold red]Error:[/bold red] Unknown attack pack '{p_clean}'. "
                f"Available packs: {', '.join(available_pack_names)}"
            )
            sys.exit(2)

    combined_excludes = list(test_suite.exclude_attacks) + list(cli_excludes or [])
    chosen_min_severity = cli_min_severity if cli_min_severity is not None else test_suite.min_severity

    pack_attacks = load_attacks(
        packs=all_requested_packs,
        exclude=combined_excludes,
        min_severity=chosen_min_severity,
    )

    final_tests: list[AdversarialTest] = []
    seen_ids: set[str] = set()
    exclude_set = {x.strip().upper() for x in combined_excludes}

    custom_idx = 1
    for t in test_suite.tests:
        custom_id = t.id or f"CUSTOM-{custom_idx:03d}"
        if not t.id:
            custom_idx += 1
        if custom_id.upper() in exclude_set:
            continue
        if custom_id.upper() in seen_ids:
            continue
        seen_ids.add(custom_id.upper())
        final_tests.append(
            AdversarialTest(
                name=t.name,
                input=t.input,
                id=custom_id,
                category=t.category,
                severity=t.severity,
                success_markers=t.success_markers,
                success_regex=t.success_regex,
            )
        )

    for atk in pack_attacks:
        if atk.id.upper() in seen_ids or atk.id.upper() in exclude_set:
            continue
        seen_ids.add(atk.id.upper())
        final_tests.append(
            AdversarialTest(
                name=atk.name,
                input=atk.input,
                id=atk.id,
                category=atk.category,
                severity=atk.severity,
                success_markers=atk.success_markers,
                success_regex=atk.success_regex,
            )
        )

    if not final_tests:
        console.print("[bold red]The 'tests' list cannot be empty. At least one adversarial test is required.[/bold red]")
        sys.exit(2)

    return final_tests, all_requested_packs


def setup_evaluation_clients(
    target_backend: str,
    judge_backend: str,
    model: str,
    actual_judge_model: str,
    actual_patch_model: str,
    target_base_url: str | None,
    judge_base_url: str | None,
    host: str,
    timeout: float,
    api_key_env: str,
    mock: bool,
) -> tuple[Any, Any, Any]:
    """Initialize and run preflight checks for target, judge, and patcher clients."""
    if target_backend == "ollama" and judge_backend == "ollama":
        distinct_models: list[str] = []
        for m in [model, actual_judge_model, actual_patch_model]:
            if m not in distinct_models:
                distinct_models.append(m)
        client = preflight(distinct_models, host=host, timeout=timeout, mock=mock)
        return client, client, client

    from guard_rail_edge.backends import get_backend

    target_client: Any = None
    judge_client: Any = None
    patch_client: Any = None

    if target_backend == "openai":
        target_client = get_backend(
            backend_type="openai",
            model=model,
            base_url=target_base_url,
            timeout=timeout,
            api_key_env=api_key_env,
            mock=mock,
        )
        if not mock:
            try:
                target_client.preflight(model)
            except EvaluatorConnectionError as exc:
                console.print(
                    Panel(
                        str(exc),
                        title=f"[bold red]Target Backend Pre-Flight Check Failed ({model})[/bold red]",
                        border_style="red",
                    )
                )
                sys.exit(2)
    else:
        target_client = preflight([model], host=host, timeout=timeout, mock=mock)

    if judge_backend == "openai":
        judge_client = get_backend(
            backend_type="openai",
            model=actual_judge_model,
            base_url=judge_base_url,
            timeout=timeout,
            api_key_env=api_key_env,
            mock=mock,
        )
        patch_client = get_backend(
            backend_type="openai",
            model=actual_patch_model,
            base_url=judge_base_url,
            timeout=timeout,
            api_key_env=api_key_env,
            mock=mock,
        )
        if not mock:
            try:
                judge_client.preflight(actual_judge_model)
            except EvaluatorConnectionError as exc:
                console.print(
                    Panel(
                        str(exc),
                        title=f"[bold red]Judge Backend Pre-Flight Check Failed ({actual_judge_model})[/bold red]",
                        border_style="red",
                    )
                )
                sys.exit(2)
    else:
        j_models = [actual_judge_model]
        if actual_patch_model not in j_models:
            j_models.append(actual_patch_model)
        judge_client = preflight(j_models, host=host, timeout=timeout, mock=mock)
        patch_client = judge_client

    return target_client, judge_client, patch_client
