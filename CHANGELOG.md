# Changelog

All notable changes to the `guard-rail-edge` project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.5.3] - 2026-10-31

### Fixed
- Fixed: removed unsourced wall times from results table; verdict text and rows now generated from raw reports; legacy review column shows n/a.

## [0.5.2] - 2026-10-31

### Fixed
- Fixed: verdict now requires overall AND holdout thresholds; gpt-oss-120b re-labelled NOT TRUSTWORTHY.
- Rationale: End users don't tune on our dataset, so the overall set is the main estimate; the holdout split guards against evaluator prompt tuning.

### Added
- Added review-rate column ("Safe cases sent to review") with Wilson confidence intervals to calibration tables in `README.md` and documentation.
- Added `--rescore` flag to `guard-rail-edge calibrate` to recompute metrics and verdicts from existing raw report JSON files without calling model backends.
- Added non-determinism note in documentation for reasoning models across repeat runs.

## [0.5.1] - 2026-10-31

### Security
- **Strict Benchmark Provenance Rule & Removal of Un-Evaluated Rows**:
  - Removed all rows and references to models that were not empirically evaluated (`mistral:7b`, `llama3:8b`, `deepseek-r1:7b`, `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`).
  - Enforced structural provenance: every benchmark row must derive directly from a committed raw JSON report in `docs/data/raw/` or an archived legacy result in `docs/data/legacy_results.json` tracing to commit `101a81e`.
  - Added `tests/test_results_integrity.py` asserting no unverified models exist in benchmark data or documentation and verifying that raw reports contain zero API keys.

### Added
- **Official Composite GitHub Action (`action.yml`)**:
  - Automated CI/CD security gate supporting inputs for test suite, configuration file, judge backend/model, package version, step policies (`on-review`), and report output paths.
  - Generates rich Markdown job summaries embedded in `$GITHUB_STEP_SUMMARY` displaying verdict badges, metric breakdowns, detected vulnerability tables, and self-healing patch links.
  - Automatically uploads evaluation reports and auto-patch `.patch` artifacts.
  - Added self-test workflow `.github/workflows/action-selftest.yml` and comprehensive guide `docs/github-action.md`.
- **First-Run Friendly Guidance**:
  - `doctor` and `run` now surface a friendly quickstart hint when executed in an unconfigured directory without command-line model overrides: `"No configuration found. Quick start: guard-rail-edge init --preset groq (free hosted judge) or init --preset mock (offline demo)."`.

### Fixed
- Removed calibration rows for models that were not actually evaluated (added in 9a2f9e0); results are now generated from archived raw reports; corrected confidence intervals.

### Changed
- **Automated Benchmark Generation (`scripts/build_results.py`)**:
  - Benchmark tables in `docs/real-model-results.md`, `README.md`, and `docs/data/judge_calibration.json` are now dynamically built from raw evaluation reports with correctly parameterized 95% Wilson score intervals ($n=20$ for leaks, $n=20$ for false alarms).
  - Legacy local runs from commit `101a81e` are distinctly labeled and visually distinguished with hatching/tint in `assets/judge-calibration.svg`.

---

## [0.5.0] - 2026-10-30

### Added
- **Layered Configuration Support (`guard_rail_edge/config.py`)**:
  - Full TOML configuration loaded in strict precedence: built-in defaults -> `[tool.guard-rail-edge]` in `pyproject.toml` -> `guard-rail-edge.toml` (or `--config PATH`) -> CLI flags.
  - Unknown configuration keys trigger an informative error and exit code 2.
  - Run header prints `Config: <path>` whenever a configuration file is active.
- **`guard-rail-edge doctor` Command**:
  - Preflight environment diagnostics checking Python version, package version, configuration validity, credential presence (`SET`/`NOT SET`), Ollama connectivity, test suite validity, judge independence, and empirical calibration status.
- **`guard-rail-edge init --preset groq|ollama|mock`**:
  - Scaffolds both `tests.json` and a commented `guard-rail-edge.toml` tailored for Groq free tier, local Ollama, or offline mock modes.
- **Realistic Example Suites (`examples/`)**:
  - Added runnable, realistic suites in `examples/support-bot/`, `examples/rag-assistant/`, `examples/internal-hr-bot/`, and `examples/json-api-agent/`, each with `tests.json`, `guard-rail-edge.toml`, and README documentation.
- **Empirical Calibration Visualizations**:
  - Generated `assets/judge-calibration.svg` from benchmark data in `docs/data/judge_calibration.json` with 95% Wilson confidence intervals.
  - Recorded realistic terminal demo `assets/demo.svg` via Rich console recording.
- **Documentation Architecture Split**:
  - Split comprehensive reference materials into `docs/cli-reference.md`, `docs/configuration.md`, `docs/attack-library.md`, `docs/calibration.md`, and `docs/backends.md`.
- **Launch Hygiene**:
  - Added `SECURITY.md`, `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), issue templates (`bug_report.md`, `feature_request.md`, `new_attack.md` with harmless-goal rule), PR template, and `CITATION.cff`.

### Changed
- **README.md Overhaul**:
  - Completely rewritten around calibrated AI judges, under 250 lines, leading with *"Prompt-injection testing for CI/CD that measures whether its own AI judge can be trusted"*.
  - Updated Quickstart to recommend the free Groq preset instead of uncalibrated local models.
  - Added neutral, factual comparison against promptfoo, garak, PyRIT, and DeepTeam.

### Fixed
- Fixed pytest pythonpath resolution for top-level scripts across cross-platform environments.
- Corrected cross-platform path resolution in markdown link integrity tests.

---

## [0.4.1] - 2026-10-30

### Changed
- Removed Windows registry key (`winreg`) fallback from `OpenAIBackend`. API keys are now exclusively resolved from environment variables (`os.environ`), matching all other platforms and avoiding stale credentials or unexpected lookups. Missing keys now provide clear restart guidance (`setx`).
- Added 95% Wilson confidence intervals in pure Python next to leak detection rates and false alarm rates across overall and holdout splits in `guard-rail-edge calibrate` and report JSON.
- Separated judge retry metrics: renamed retries row/label to "Judge Parse Retries" (tracking unparseable re-asks) and added dedicated "Rate-Limit Waits" counter tracking HTTP 429/503 backoffs.
- Updated README and documentation with honest wording (replacing "Certified" with "passed calibration") and added sample-size caveat beneath calibration tables.
- Added Recommended Setup box after Quickstart in README.

---

## [0.4.0] - 2026-10-27

### Added
- **"NEEDS REVIEW" Verdict & Exit Code 3**:
  - Added 4-tier verdict hierarchy: `JAILBROKEN (2) > NEEDS REVIEW > SUSPICIOUS (1) > SAFE (0)`.
  - Added `needs_review: bool` and `review_reasons: list[str]` attributes to `TestResult`.
  - Added `--on-review fail|warn` (default: `fail`). Under `fail`, any test flagged `NEEDS REVIEW` fails the CI/CD pipeline with Exit Code 3 (unless confirmed score 2 jailbreaks trigger Exit Code 1).
  - Exit code priority: `2 (Tool/Infra Error) > 1 (Vulnerabilities) > 3 (Needs Review) > 0 (Pass)`.
  - Updated summary banners and JSON reports with `needs_review_count`, per-test `needs_review`, and `review_reasons`.
  - Self-healing prompt hardening (`--auto-patch` / `--apply`) incorporates traces from `needs_review` tests when `--on-review fail`.
- **Automatic Per-Run Canary**:
  - Automatically generates a unique secret canary `GRE-<10HEX>` appended to the target system prompt only.
  - Detects verbatim leaks deterministically in code (case-insensitive, separator-agnostic, and contiguous 8+ hex digits) as Score 2 (`auto-canary`).
  - Secret canary is strictly excluded from judge prompts, reports (stored as SHA-256 only), patches, and `--apply` hardened prompts.
  - Can be disabled via `--no-auto-canary`.
- **Fuzzy Overlap Check (Paraphrase & Summary Detection)**:
  - Added zero-dependency module `guard_rail_edge/overlap.py` evaluating 3-gram and distinctive term overlap between prompt and response.
  - Escalates potential paraphrased leaks to `NEEDS REVIEW` when overlap ratio &ge; 0.45.
  - Adheres strictly to the escalation-only principle: never lowers scores and never assigns score 2 directly.
  - Added `guard-rail-edge calibrate --checks-only` to run deterministic and overlap checks offline without constructing or invoking backends.
  - Configurable via `--overlap-threshold FLOAT` and `--no-overlap-check`.
- **Two-Judge Ensemble & Disagreement Handling**:
  - Added `--second-judge-model`, `--second-judge-backend`, and `--second-judge-base-url`.
  - Added `--disagreement-policy review|max` (default: `review`). Disagreements between judges route to `NEEDS REVIEW`.
  - Non-unanimous self-consistency votes (`--judge-votes N > 1`) escalate to `NEEDS REVIEW`.
  - Added per-test `judge_scores` dictionary in JSON reports.
  - Added ensemble calibration metrics (Leak Catch Rate, Missed Leak Rate, False Alarm Rate, Review Rate) and `TRUSTWORTHY (WITH REVIEW)` calibration verdict.
- **Judge Response Cache & Parse Failure Mitigation**:
  - Added content-addressed judge cache (`guard_rail_edge/cache.py`) via `--judge-cache DIR` (default `.guard-rail-edge-cache/` for calibrate).
  - Added `--debug-judge` CLI flag to output raw unparseable judge responses to stderr and include them in the JSON report.
  - Created resilient JSON parser (`guard_rail_edge/parser.py`) stripping reasoning `<think>` tags, markdown code blocks, trailing commas, and providing regex key-value extraction fallback.
- **Free Hosted Judge Presets & Rate Limiting**:
  - Added provider presets in `guard_rail_edge/backends/presets.py` for `groq`, `openrouter`, `gemini`, and `github`.
  - Implemented automatic request throttling (`--max-rpm`) and exponential backoff (2s, 4s, 8s, 16s, 32s) honoring HTTP 429/503 `Retry-After` headers.
  - Added `guard-rail-edge models --backend <preset>` to list available models securely without exposing credentials.

### Changed
- **Report Schema Version**: Bumped `report_schema_version` to `"2"` in JSON reports to reflect `needs_review_count`, `needs_review`, `review_reasons`, and `judge_scores`.
- **Default Review Policy**: `--on-review` defaults to `fail` (escalates uncertain signals to block pipeline at Exit Code 3 rather than guessing PASS).
- **Default Disagreement Policy**: `--disagreement-policy` defaults to `review` (disagreements route to human review rather than guessing).
- **Default Calibrate Cache**: `guard-rail-edge calibrate` defaults to caching judge replies in `.guard-rail-edge-cache/` to eliminate re-run costs.
- **Default Auto-Canary**: Automatic per-run canary is enabled by default to catch translation/verbatim leaks in code.

---

## [0.3.2] - 2026-10-26

### Fixed
- **Calibrate Judge Calling & Label Leak Prevention**:
  - Fixed: calibrate returned ground-truth labels instead of judge verdicts in non-mock mode (introduced in a95cf43). Calibration results published in 0.3.1 for qwen2.5:7b were invalid.
  - Removed `expected_score` parameter from `grade_interaction()` entirely so production grading code never receives ground-truth labels.
  - Added integrity regression test suite (`tests/test_calibrate_integrity.py`) validating offline fake judge responses, wire HTTP calls via `OpenAIBackend`, and static signature/code checks preventing label leakage.
  - Updated mock calibration to route benchmark labels only through an oracle backend when `--mock` is explicitly enabled.

---

## [0.3.1] - 2026-10-26

### Added
- **Proven TRUSTWORTHY Judge (`qwen2.5:7b`)**:
  - Validated `qwen2.5:7b` via `guard-rail-edge calibrate` against the 50-case benchmark dataset: 100.0% overall accuracy, 100.0% leak detection rate (recall), 0.0% false alarm rate, 0 evaluation errors, and 0 retries.
  - End-to-end smoke test validated against target `qwen2.5:0.5b`: `safe_tests.json` scores 100% safe (all score 0, exit 0), and `leaky_target_tests.json` detects breach (score 2, exit 1).
  - Officially recommended `qwen2.5:7b` as the primary local `--judge-model`.
- **Backend Model Call Abstraction**:
  - Completed `ChatBackend` routing across evaluator, runner, and patcher pipelines.
  - Added dedicated test coverage for `OllamaBackend`, `MockBackend`, and backend factory (`tests/test_backends.py`).

### Changed
- **Documentation Consistency**:
  - Aligned documentation across README, `docs/real-model-results.md`, and CLI calibration thresholds: leak detection rate $\ge 80\%$, false alarm rate $\le 15\%$, and 0 evaluation errors.
  - Same-model warning now recommends proven calibrated model `qwen2.5:7b`.

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
