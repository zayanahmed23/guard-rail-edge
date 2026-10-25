"""CLI entrypoint and public interface for guard-rail-edge."""

import sys

# Configure Windows consoles for safe UTF-8 output
if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from guard_rail_edge.cli import DefaultGroup, app
from guard_rail_edge.cli.init import STARTER_SUITE_CONTENT
from guard_rail_edge.evaluator import (
    EvaluationError,
    EvaluatorConnectionError,
    check_format,
    grade_interaction,
    run_target_simulation,
    verify_ollama_ready,
)
from guard_rail_edge.patcher import (
    create_unified_patch,
    generate_hardened_prompt,
    read_text_exact,
    render_hardened_suite,
    write_text_exact,
)
from guard_rail_edge.render import (
    console,
    format_score_badge,
    render_evaluation_results,
    render_results_table,
    render_verification_table,
)
from guard_rail_edge.report import write_report
from guard_rail_edge.runner import (
    evaluate_suite,
    heal,
    load_suite,
    preflight,
    summarize,
    verify,
)

__all__ = [
    "DefaultGroup",
    "EvaluationError",
    "EvaluatorConnectionError",
    "STARTER_SUITE_CONTENT",
    "app",
    "check_format",
    "console",
    "create_unified_patch",
    "evaluate_suite",
    "format_score_badge",
    "generate_hardened_prompt",
    "grade_interaction",
    "heal",
    "load_suite",
    "preflight",
    "read_text_exact",
    "render_evaluation_results",
    "render_hardened_suite",
    "render_results_table",
    "render_verification_table",
    "run_target_simulation",
    "summarize",
    "verify",
    "verify_ollama_ready",
    "write_report",
    "write_text_exact",
]

if __name__ == "__main__":
    app()
