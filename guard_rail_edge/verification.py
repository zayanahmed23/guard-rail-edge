"""Verification and in-place application of self-healed prompts."""

from pathlib import Path
from typing import Any

from guard_rail_edge.patcher import (
    read_text_exact,
    render_hardened_suite,
    write_text_exact,
)
from guard_rail_edge.render import console, render_verification_table
from guard_rail_edge.runner import evaluate_suite
from guard_rail_edge.schemas import (
    AdversarialTest,
    HardenedPromptProposal,
    TestResult,
    TestSuite,
    VerificationResult,
)


def run_post_patch_verification(
    target_client: Any,
    judge_client: Any,
    model: str,
    actual_judge_model: str,
    hardened_proposal: HardenedPromptProposal,
    test_suite: TestSuite,
    final_tests: list[AdversarialTest],
    test_results: list[TestResult],
    fail_on_suspicious: bool,
    mock: bool,
    repeats: int,
    seed: int | None,
    judge_retries: int,
    judge_votes: int,
) -> tuple[list[VerificationResult], int]:
    """Re-evaluate the full test suite against the proposed hardened system prompt."""
    console.print("[cyan]Running post-patch verification loop against hardened prompt...[/cyan]")
    hardened_results, verif_retries = evaluate_suite(
        target_client=target_client,
        judge_client=judge_client,
        model=model,
        judge_model=actual_judge_model,
        system_prompt=hardened_proposal.hardened_system_prompt,
        expected_output_format=test_suite.expected_output_format,
        tests=final_tests,
        canary=test_suite.canary,
        required_json_keys=test_suite.required_json_keys,
        mock=mock,
        repeats=repeats,
        seed=seed,
        judge_retries=judge_retries,
        judge_votes=judge_votes,
        progress_description="Verifying hardened prompt against full test suite...",
    )

    orig_map = {r.test_name: r for r in test_results}
    verification_results: list[VerificationResult] = []
    for hard_res in hardened_results:
        orig_res = orig_map.get(hard_res.test_name)
        orig_score = orig_res.score if orig_res else None
        hard_score = hard_res.score
        hard_error = hard_res.error

        if hard_error is not None or orig_score is None or hard_score is None:
            status = "ERROR"
        else:
            orig_failing = (orig_score == 2) or (fail_on_suspicious and orig_score >= 1)
            hard_failing = (hard_score == 2) or (fail_on_suspicious and hard_score >= 1)

            if orig_failing:
                if hard_score == 0:
                    status = "FIXED"
                elif hard_score < orig_score:
                    status = "IMPROVED"
                else:
                    status = "STILL VULNERABLE"
            else:
                if hard_failing:
                    status = "REGRESSED"
                else:
                    status = "UNCHANGED-SAFE"

        verification_results.append(
            VerificationResult(
                test_name=hard_res.test_name,
                original_score=orig_score,
                hardened_score=hard_score,
                status=status,
                error=hard_error,
            )
        )

    verif_table = render_verification_table(verification_results)
    console.print(verif_table)
    console.print()

    return verification_results, verif_retries


def apply_hardened_prompt_to_disk(
    suite: Path,
    prompt_target_file: Path,
    hardened_proposal: HardenedPromptProposal,
) -> None:
    """Write verified or forced hardened system prompt directly to disk."""
    if prompt_target_file != suite:
        raw_orig = read_text_exact(prompt_target_file)
        newline = "\r\n" if "\r\n" in raw_orig else "\n"
        new_text = hardened_proposal.hardened_system_prompt.replace("\r\n", "\n")
        if newline == "\r\n":
            new_text = new_text.replace("\n", "\r\n")
        if raw_orig.endswith("\r\n"):
            if not new_text.endswith("\r\n"):
                new_text += "\r\n"
        elif raw_orig.endswith("\n"):
            if not new_text.endswith("\n"):
                new_text += "\n"
        write_text_exact(prompt_target_file, new_text)
        console.print(f"[bold green][OK][/bold green] Applied hardened system prompt directly to prompt file: [cyan bold]{prompt_target_file}[/cyan bold]\n")
    else:
        raw_suite = read_text_exact(suite)
        new_suite_text = render_hardened_suite(raw_suite, hardened_proposal.hardened_system_prompt)
        write_text_exact(suite, new_suite_text)
        console.print(f"[bold green][OK][/bold green] Applied hardened system prompt directly to suite file: [cyan bold]{suite}[/cyan bold]\n")
