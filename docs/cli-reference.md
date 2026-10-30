# CLI Reference Manual

Comprehensive command line interface reference for `guard-rail-edge`.

## Exit Codes

`guard-rail-edge` uses deterministic process exit codes designed for automated CI/CD gating:

| Exit Code | Status | Meaning |
|:---:|---|---|
| **`0`** | **PASSED** | All adversarial tests passed security checks (Score 0 SAFE), or non-critical findings under permissive policies (`--on-review warn`). |
| **`1`** | **BLOCKED** | Security vulnerability identified (Score 2 JAILBROKEN), or policy failure (`--fail-on-suspicious`, `--fail-on-format`). |
| **`2`** | **ERROR** | Operational or execution error (e.g. invalid config file, unreachable backend, schema validation error). |
| **`3`** | **NEEDS REVIEW** | Inconclusive evaluation requiring human review under `--on-review fail` (e.g., judge disagreement, semantic overlap). |

---

## Commands

### `guard-rail-edge run [SUITE]`

Executes an adversarial prompt injection evaluation against a target model and grades outputs using deterministic checks and calibrated LLM judges.

```bash
guard-rail-edge run [SUITE_PATH] [OPTIONS]
```

#### Arguments
- `SUITE_PATH`: Optional positional path to the test suite JSON file (defaults to `tests.json` or `--suite`).

#### Options
- `--suite`, `-s` *(Path, default: `tests.json`)*: Test suite JSON file path.
- `--config`, `-c` *(Path, optional)*: Explicit TOML configuration file path.
- `--model`, `-m` *(str, default: `gemma:2b`)*: Target LLM model name.
- `--judge-model` *(str, optional)*: Evaluator judge model (defaults to `--model`).
- `--patch-model` *(str, optional)*: Self-healing prompt synthesis model.
- `--target-backend` *(str, default: `ollama`)*: Backend for target model (`ollama` or `openai`).
- `--target-base-url` *(str, optional)*: Custom base URL for target backend.
- `--judge-backend` *(str, default: `ollama`)*: Backend for evaluator judge (`ollama` or `openai`).
- `--judge-base-url` *(str, optional)*: Custom base URL for judge backend.
- `--second-judge-model` *(str, optional)*: Second judge model for cross-checking ensemble.
- `--second-judge-backend` *(str, default: `ollama`)*: Backend for second judge model.
- `--second-judge-base-url` *(str, optional)*: Custom base URL for second judge backend.
- `--disagreement-policy` *(str, default: `review`)*: Disagreement resolution: `review` or `max`.
- `--on-review` *(str, default: `fail`)*: Policy when tests require review: `fail` (exit 3) or `warn` (exit 0).
- `--api-key-env` *(str, default: `OPENAI_API_KEY`)*: Name of the environment variable holding API key.
- `--max-rpm` *(int, optional)*: Rate-limiting request throttle (requests per minute).
- `--auto-canary / --no-auto-canary` *(bool, default: `True`)*: Inject unique per-run cryptographic canary token.
- `--overlap-check / --no-overlap-check` *(bool, default: `True`)*: Detect paraphrased prompt extraction via n-gram overlap.
- `--overlap-threshold` *(float, default: `0.25`)*: Overlap Jaccard/containment threshold for review escalation.
- `--judge-always` *(bool, default: `False`)*: Always execute LLM judge even when deterministic code catches fire.
- `--judge-cache` *(Path, optional)*: Cache directory for judge responses (`.guard-rail-edge-cache/`).
- `--no-cache` *(bool, default: `False`)*: Bypass caching layer completely.
- `--judge-retries` *(int, default: `2`)*: Max retries for unparseable judge JSON output.
- `--judge-votes` *(int, default: `1`)*: Number of self-consistency voting samples.
- `--repeats` *(int, default: `1`)*: Number of test iterations per attack (max score wins).
- `--seed` *(int, optional)*: Random seed for deterministic model sampling.
- `--auto-patch`, `-p` *(bool, default: `False`)*: Enable self-healing prompt rewrite synthesis.
- `--apply` *(bool, default: `False`)*: Write verified hardened prompt back to suite file.
- `--force-apply` *(bool, default: `False`)*: Apply hardened prompt without post-patch verification.
- `--patch-output`, `-o` *(Path, optional)*: Destination file for `.patch` unified diff.
- `--verify-patch / --no-verify-patch` *(bool, default: `True`)*: Re-run test suite to confirm patch fix.
- `--fail-on-suspicious` *(bool, default: `False`)*: Block CI (exit 1) on Score 1 SUSPICIOUS findings.
- `--fail-on-format` *(bool, default: `False`)*: Block CI (exit 1) on structured format failures (e.g. invalid JSON).
- `--pack` *(list[str], optional)*: Built-in attack packs to merge (`system_prompt_leakage`, `roleplay_bypasses`, `format_breakout`, `obfuscation`, or `all`).
- `--min-severity` *(str, default: `low`)*: Minimum attack severity filter (`low`, `medium`, `high`).
- `--exclude` *(list[str], optional)*: Attack IDs to omit from execution.
- `--mock` *(bool, default: `False`)*: Simulated offline mode without GPU or network requests.
- `--report-json` *(Path, optional)*: Machine-readable JSON report output path.
- `--debug-judge` *(bool, default: `False`)*: Print raw unparseable judge replies to stderr.
- `--verbose`, `-v` *(bool, default: `False`)*: Enable detailed debugging logs.

---

### `guard-rail-edge init`

Scaffolds a new test suite file and a commented `guard-rail-edge.toml` configuration.

```bash
guard-rail-edge init [OPTIONS]
```

- `--preset` *(choice: `groq`, `ollama`, `mock`, default: `ollama`)*: Template configuration preset.
- `--output`, `-o` *(Path, default: `tests.json`)*: Destination path for test suite JSON.
- `--force`, `-f` *(bool, default: `False`)*: Overwrite existing files if present.

---

### `guard-rail-edge doctor`

Runs a pre-flight system diagnostics and environment checklist to ensure readiness for automated evaluation.

```bash
guard-rail-edge doctor [OPTIONS]
```

- `--config`, `-c` *(Path, optional)*: Configuration file path to inspect.
- `--suite`, `-s` *(Path, default: `tests.json`)*: Test suite file to validate.

#### Checks Performed
1. **Python Version**: Confirms Python >= 3.11.
2. **Package Version**: Reports installed version of `guard-rail-edge`.
3. **Configuration**: Verifies `pyproject.toml` and `guard-rail-edge.toml` for unknown keys.
4. **Credentials**: Reports `SET` or `NOT SET` for supported provider keys (never prints values).
5. **Engine Connectivity**: Verifies Ollama connectivity on configured host port.
6. **Test Suite**: Checks JSON syntax and Pydantic schema validation.
7. **Judge Independence**: Warns if target and judge models are identical.
8. **Judge Calibration**: Checks whether selected judge has passed calibration benchmarks.

---

### `guard-rail-edge calibrate`

Evaluates LLM judge accuracy, leak recall, and false alarm rate against the 50-case ground-truth benchmark.

```bash
guard-rail-edge calibrate [OPTIONS]
```

- `--judge-model` *(str, optional)*: Model to benchmark as judge.
- `--judge-backend` *(str, default: `ollama`)*: Backend provider (`ollama` or `openai`).
- `--second-judge-model` *(str, optional)*: Benchmark two-judge ensemble.
- `--checks-only` *(bool, default: `False`)*: Benchmark deterministic checks and overlap heuristic without LLM calls.
- `--dev-only` *(bool, default: `False`)*: Run only development split (30 cases).
- `--holdout-only` *(bool, default: `False`)*: Run only holdout split (20 cases).
- `--judge-cache` *(Path, optional)*: Enable caching of raw judge responses.
- `--report-json` *(Path, optional)*: Export calibration metrics to JSON.

---

### `guard-rail-edge attacks`

Inspects and exports curated adversarial attack packs from the built-in library.

```bash
guard-rail-edge attacks list
guard-rail-edge attacks info <ATTACK_ID>
guard-rail-edge attacks dump <PACK_NAME>
```

---

### `guard-rail-edge models`

Lists accessible models from connected backends without sending credentials to external logs.

```bash
guard-rail-edge models --backend groq
guard-rail-edge models --backend ollama
```

