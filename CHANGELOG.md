# Changelog

All notable changes to the `guard-rail-edge` project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.3.0] - 2026-10-25

### Added
- **OpenAI-Compatible Backend (`guard_rail_edge.backends`)**:
  - Implemented zero-dependency `OpenAIBackend` using standard library `urllib.request`.
  - Added CLI options `--target-backend [ollama|openai]`, `--judge-backend [ollama|openai]`, `--target-base-url`, `--judge-base-url`, and `--api-key-env`.
  - Supports vLLM, Ollama OpenAI endpoints, LiteLLM, OpenAI, Groq, OpenRouter, and any OpenAI-compatible API.
  - Automatically suppresses and redacts API keys from all logs, exceptions, and CI artifacts.
- **Judge Model Calibration (`guard-rail-edge calibrate`)**:
  - New CLI command to benchmark and verify whether an LLM judge model is trustworthy before using it for security evaluations.
  - Computes 3x3 confusion matrix, leak detection rate (recall), and false alarm rate against expert-labeled ground truth calibration set.
  - Certifies judge as `TRUSTWORTHY` when leak detection rate >= 80%, false alarm rate <= 15%, and evaluation errors equal 0.
- **Judge Calibration Dataset (50 Cases)**:
  - Hand-crafted, balanced ground truth calibration set packaged in `guard_rail_edge/calibration/judge_calibration.json` with 20 safe cases (0), 10 suspicious cases (1), and 20 jailbroken cases (2), split 60% dev and 40% holdout.
  - Over 60% of score-2 cases strictly test semantic reasoning without deterministic shortcuts.
- **Calibrated Judge Prompt with Sequential Decision Procedure & Voting**:
  - Restructured `AUDITOR_META_PROMPT` into a step-by-step sequential decision procedure with 6 concrete few-shot examples (2 per rubric score).
  - Puts the `score` field FIRST in JSON output to anchor the model's reasoning before token generation.
  - Added `--judge-votes N` self-consistency voting (majority vote across N evaluations) for high-stakes evaluations.
- **Deterministic Attack Detection & Canary Scoring**:
  - Added `success_markers` and `success_regex` to `AttackModel` and `AdversarialTest` schemas, allowing code checks to identify objectively checkable exploit successes with zero judge variance.
  - Added `--judge-always` CLI flag to run the judge model even when a deterministic check triggers, recording judge reasoning while keeping `max(deterministic, judge)` score.
  - Added `detection` field (`marker`, `regex`, `canary`, `verbatim`, `judge`) to results and summary tables to track verdicts derived from deterministic code vs LLM judges.
- **Format Failure Enforcement (`--fail-on-format`)**:
  - Added `--fail-on-format` CLI flag to optionally fail CI/CD pipeline (exit 1) on output format violations.
  - Summary banner and machine-readable reports now clearly display format failures and enforcement policy (`enforced` vs `report-only`).
- **Modular Codebase Architecture**:
  - Split monolithic `main.py` into focused, single-responsibility modules under `guard_rail_edge/` and `guard_rail_edge/cli/`, each strictly under 450 lines.
  - Test coverage on `patcher.py` increased to 96%, with overall repository coverage reaching ~90%.

### Changed
- **Format Validity Separated from Security Score**: Programmatic format failures no longer raise the security score except for attacks in the `format-evasion` category where breaking format is the attack goal. Use `--fail-on-format` for the old strictness where format violations fail the pipeline.

---

## [0.2.0] - 2026-10-25

### Features & Security
- **Curated Built-In Attack Library (8 Packs, 48 Attacks)**: Shipped an extensible library of 48 categorized, curated prompt injection, evasion, and jailbreak vectors packaged as JSON package data (`guard_rail_edge/attacks/*.json`).
  - `prompt-extraction` (6 attacks): Direct verbatim leakage, translation probes, role dumps, and transcript boundary extractions.
  - `instruction-override` (6 attacks): Priority override claims, fake admin/maintenance directives, boundary escapes, and context resets.
  - `persona-hijack` (6 attacks): DAN-style jailbreaks, hypothetical world simulations, opposite mode, and emotional grandma exploit framing.
  - `format-evasion` (6 attacks): Markdown, XML, CSV, and dual response evasion testing strict JSON schema compliance.
  - `obfuscation` (6 attacks): Base64, ROT13, Leetspeak, whitespace fragmentation, reversed text, and Unicode zero-width space smuggling.
  - `multilingual` (6 attacks): Cross-lingual transfer attacks in Spanish, French, German, Arabic, Urdu, and Simplified Chinese.
  - `indirect-injection` (6 attacks): Hidden injections inside HTML comments, customer reviews, logs, and forwarded emails.
  - `secret-exfiltration` (6 attacks): Canary probing, partial prefix leakage, character length querying, and credential audit attempts.
- **Harmless Goal Security Constraint**: All built-in attacks strictly test whether target models violate their own system prompt constraints (prompt leakage, persona deviations, format violations, off-topic drift). The goal of every payload is completely harmless (e.g. reciting a pirate poem, outputting XML, revealing placeholder discount codes). Zero real-world hazardous or malicious payloads are included.
- **Suite & CLI Pack Integration**: Added `packs`, `exclude_attacks`, and `min_severity` fields to `TestSuite`. Added `--pack`, `--exclude`, and `--min-severity` CLI overrides on `run`. Added `CUSTOM-001`... auto-assignment for custom tests without IDs. Added `--with-packs` to `guard-rail-edge init`.
- **Attack Library CLI (`guard-rail-edge attacks`)**: Added `attacks list [--pack NAME] [--category X]` and `attacks show ID` CLI subcommands for browsing and inspecting attacks.
- **Category Breakdown & ID Column**: Added `ID` and `Category` columns to the terminal evaluation matrix with category grouping, and per-category breakdown metrics to the summary banner.

---

## [0.1.3] - 2026-10-25

### Improvements
- **Vary Judge Retry Temperature and Seed**: Initial judge attempt runs at temperature 0.0 with user-specified seed. Retries (attempts >= 1) dynamically use temperature 0.3 and increment seed (`seed + attempt`) to avoid repeating identical deterministic failures while maintaining reproducibility.

---

## [0.1.2] - 2026-10-25

### Bug Fixes & Reliability
- **Cross-Platform Exact Line Endings**: Added `read_text_exact()` and `write_text_exact()` helpers using `newline=""` to prevent universal newline translation. Unified diffs generated with `lineterm=newline` now preserve CRLF/LF line endings exactly across both Linux and Windows, fixing `git apply --check` failures on Ubuntu CI runners and preventing whole-file line-ending churn during `--apply`.
- **Judge Evaluation Retries**: Added `--judge-retries INT` (default 2). On parsing failure or call exception, the evaluator retries up to `judge_retries` times, alternating between structured output (`format=schema`) and unstructured output, before failing closed. Recorded `judge_retry_count` in the CI/CD evaluation report.
- **Judge Model Warning**: If `--judge-model` equals `--model`, a yellow warning is printed advising users to configure a stronger independent judge model (e.g. `qwen2.5:7b`, `llama3.1:8b`) to prevent biased scoring.
- **Robust Deterministic Leak Detection**: `check_deterministic_leaks()` now normalizes case (lowercase) and collapses whitespace runs to a single space before sliding window verification, reliably detecting system prompt leaks despite uppercase formatting, extra newlines, or indentation.
- **Isolated Packaging Test**: `test_wheel_contains_only_package_files` copies the project into an isolated `tmp_path` directory (excluding `.git`, `build`, `dist`, `*.egg-info`, `.venv`) before building the wheel, preventing leftover artifacts from polluting wheel verification. Registered `@pytest.mark.slow`.

---

## [0.1.1] - 2026-10-24

### Security & Hardening
- **Fail-Closed Infrastructure**: Infrastructure errors (Ollama connection errors, timeouts, unparseable judge responses) now raise `EvaluationError` and exit with code 2 instead of silently passing as safe.
- **Judge & Patcher Isolation**: Added `--judge-model` and `--patch-model` CLI options to decouple evaluator judge and patcher models from the target model. Pre-flight checks verify all distinct models before execution.
- **Prompt Injection Defense in Meta-Prompts**: Untrusted target responses and attack traces are now isolated using per-call cryptographically random boundary tags (`<untrusted_{tag}>...</untrusted_{tag}>`), with tag stripping to prevent prompt breakout attacks.
- **Deterministic Leak Checks**: Added canary token detection (`canary` field in suite) and contiguous 60+ character verbatim system prompt leak detection running independently in code before LLM evaluation.
- **Meaningful Full-Suite Verification**: Post-patch verification re-runs the entire suite against the hardened prompt, tracking `FIXED`, `IMPROVED`, `STILL VULNERABLE`, `REGRESSED`, and `UNCHANGED-SAFE` statuses.
- **Safe Patch Gating**: `--apply` is strictly gated to write to disk only if verification confirms zero still-vulnerable tests, zero regressions, and zero errors (overridable with `--force-apply`).
- **Response Redaction**: Added `--redact-responses` flag to truncate target responses to first 80 characters + `...[redacted]` in JSON reports, preventing confidential prompt leakage into CI artifacts.

### Features & CLI Options
- **Repeats & Seeds**: Added `--repeats N` (min 1) to test non-deterministic models across multiple runs (worst-case score taken; all runs recorded in report) and `--seed INT` passed to Ollama.
- **External Prompt Files**: Test suites can specify `system_prompt_file: "path/to/prompt.txt"` relative to the suite JSON instead of an inline `system_prompt`. Patches and `--apply` target the prompt text file directly.
- **Structured JSON Validation**: Added `required_json_keys` to `TestSuite` schema; `check_format()` verifies parsed output is a dictionary containing all mandatory keys and accepts fenced ` ```json ` blocks.
- **Disable-able Verification**: Added `--verify-patch / --no-verify-patch` CLI flag (defaults to enabled). `--apply` with `--no-verify-patch` requires `--force-apply`.
- **Configurable Timeout**: Added `--timeout FLOAT` (default 120s) passed to `ollama.Client` to prevent CI hanging.
- **Version Flag**: Added `--version` / `-v` flag to CLI and `python -m guard_rail_edge --version`.

### Bug Fixes & Refactoring
- **Package Cleanliness**: Removed top-level module pollution (`main.py`, `schemas.py`, `evaluator.py`, `patcher.py`, and root `tests.json`). Added `guard_rail_edge/__main__.py`.
- **Subfolder Unified Patches**: Diff headers in generated `.patch` files are computed relative to git repository root using `git rev-parse --show-toplevel` (POSIX separators, no fake timestamps), ensuring `git apply --check` succeeds from the repo root.
- **Unified Disk Rendering**: Consolidated JSON suite rewriting into `render_hardened_suite()`, preserving line endings (LF/CRLF), indentation (tabs/spaces), unicode, and trailing newlines.
- **Honest Mock Mode**: Regex matching now uses word boundaries (`\bdan\b`, `\bignore\b`, `\boverride\b`) and hardened mock simulation requires the exact marker `### [HARDENED SECURITY BOUNDARY]`. Mock output clearly banners simulated execution.
- **Strict Model Matching**: `verify_ollama_ready()` strictly matches exact tags or `:latest` (e.g. `gemma` matches only `gemma` or `gemma:latest`, not `gemma:7b`).
- **Modular CLI Architecture**: Refactored `main.run()` into modular functions (`load_suite`, `preflight`, `evaluate_suite`, `summarize`, `heal`, `write_report`).
- **Dependencies**: Bumped `ollama>=0.5.0` for structured output schemas. Added `ruff`, `mypy`, `pytest-cov` to dev dependencies.

---

## [0.1.0] - 2026-10-24

### Initial Release
- Initial implementation of guard-rail-edge CLI tool with Typer, Rich, and Ollama integration.
- Automated prompt injection testing against LLM system prompts.
- Self-healing prompt hardening proposal generator.
- Machine-readable CI/CD report artifact export (`--report-json`).
