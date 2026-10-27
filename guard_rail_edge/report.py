"""CI/CD machine-readable evaluation report building and persistence."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import guard_rail_edge
from guard_rail_edge.patcher import write_text_exact
from guard_rail_edge.render import console
from guard_rail_edge.schemas import (
    EvaluationReport,
    HardenedPromptProposal,
    TestResult,
    VerificationResult,
)


def write_report(
    report_json: Path,
    suite: Path,
    model: str,
    judge_model: str,
    patch_model: str,
    test_results: list[TestResult],
    safe_count: int,
    suspicious_count: int,
    jailbroken_count: int,
    format_failure_count: int,
    error_count: int,
    pipeline_passed: bool,
    saved_patch_path: Path | None,
    hardened_proposal: HardenedPromptProposal | None,
    hardening_source: str | None,
    verification_results: list[VerificationResult] | None,
    fail_on_suspicious: bool,
    fail_on_format: bool = False,
    mock: bool = False,
    redact_responses: bool = False,
    judge_retry_count: int = 0,
    packs: list[str] | None = None,
    target_backend: str = "ollama",
    target_base_url: str | None = None,
    judge_backend: str = "ollama",
    judge_base_url: str | None = None,
    needs_review_count: int = 0,
    auto_canary_used: bool = False,
    auto_canary_hash: str | None = None,
    auto_canary: str | None = None,
    judge_cache_hits: int = 0,
    debug_judge_failures: list[dict[str, Any]] | None = None,
) -> EvaluationReport:
    """Generate and write machine-readable CI/CD report JSON artifact."""
    final_results = []
    for r in test_results:
        if redact_responses and r.target_response:
            resp_text = r.target_response
            if auto_canary and auto_canary in resp_text:
                resp_text = resp_text.replace(auto_canary, "[CANARY_REDACTED]")
            if auto_canary and "-" in auto_canary:
                hex_p = auto_canary.split("-", 1)[-1]
                if hex_p in resp_text:
                    resp_text = resp_text.replace(hex_p, "[CANARY_HEX_REDACTED]")
            r_dict = r.model_dump()
            r_dict["target_response"] = resp_text[:80] + "...[redacted]"
            final_results.append(TestResult(**r_dict))
        else:
            final_results.append(r)

    policy_str = "enforced" if fail_on_format else "report-only"
    threshold_desc = (
        f"{'Score >= 1 (Strict)' if fail_on_suspicious else 'Score == 2 (Jailbreak)'} | Format: {policy_str}"
    )

    code_det_count = sum(1 for r in test_results if r.detection in ("marker", "regex", "canary", "auto-canary", "verbatim"))
    judge_det_count = sum(1 for r in test_results if r.detection == "judge" or r.detection is None)

    report = EvaluationReport(
        report_schema_version="2",
        suite_path=str(suite),
        model=model,
        judge_model=judge_model,
        patch_model=patch_model,
        target_backend=target_backend,
        target_base_url=target_base_url,
        judge_backend=judge_backend,
        judge_base_url=judge_base_url,
        total_tests=len(test_results),
        safe_count=safe_count,
        suspicious_count=suspicious_count,
        jailbroken_count=jailbroken_count,
        needs_review_count=needs_review_count,
        format_failure_count=format_failure_count,
        error_count=error_count,
        pipeline_passed=pipeline_passed,
        patch_generated=str(saved_patch_path) if saved_patch_path else None,
        hardened_prompt=hardened_proposal.hardened_system_prompt if hardened_proposal else None,
        security_improvements=hardened_proposal.security_improvements if hardened_proposal else [],
        hardening_source=hardening_source,
        verification=verification_results,
        tool_version=guard_rail_edge.__version__,
        timestamp_utc=datetime.now(UTC).isoformat(),
        threshold="suspicious" if fail_on_suspicious else "jailbreak",
        threshold_description=threshold_desc,
        format_policy=policy_str,
        mock=mock,
        judge_retry_count=judge_retry_count,
        code_detection_count=code_det_count,
        judge_detection_count=judge_det_count,
        auto_canary_used=auto_canary_used,
        auto_canary_hash=auto_canary_hash,
        judge_cache_hits=judge_cache_hits,
        debug_judge_failures=debug_judge_failures or [],
        packs=packs or [],
        results=final_results,
    )

    write_text_exact(report_json, report.model_dump_json(indent=2) + "\n")
    console.print(f"[bold green][OK][/bold green] CI/CD machine-readable report exported to: [cyan bold]{report_json}[/cyan bold]\n")
    return report
