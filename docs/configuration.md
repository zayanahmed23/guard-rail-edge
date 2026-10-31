# Configuration Guide

`guard-rail-edge` supports layered, reproducible configuration via TOML files and environment variables, eliminating the need for long command-line flag sequences.

## Configuration Precedence

Settings are resolved in strict hierarchical order (later levels override earlier ones):

```
1. Built-in CLI Defaults
         ↓
2. [tool.guard-rail-edge] section in pyproject.toml
         ↓
3. guard-rail-edge.toml in the current directory (or explicit --config PATH)
         ↓
4. Command Line Flags (Explicit CLI arguments always take highest precedence)
```

If an active configuration file contains unrecognized keys, `guard-rail-edge` aborts immediately with a descriptive error message and exit code `2`.

---

## Configuration Keys

All configuration keys mirror CLI option names with underscores:

| Key | Type | Description | Default |
|---|---|---|---|
| `suite` | `str` | Path to adversarial test suite JSON file | `"tests.json"` |
| `model` | `str` | Target LLM model name | `"gemma:2b"` |
| `judge_model` | `str` | Evaluator judge model | `None` (mirrors `model`) |
| `patch_model` | `str` | Patch synthesis model | `None` (mirrors `judge_model`) |
| `target_backend` | `str` | Target backend: `"ollama"` or `"openai"` | `"ollama"` |
| `target_base_url`| `str` | Target API base URL | `None` |
| `judge_backend` | `str` | Judge backend: `"ollama"` or `"openai"` | `"ollama"` |
| `judge_base_url` | `str` | Judge API base URL | `None` |
| `second_judge_model` | `str` | Cross-checking ensemble model | `None` |
| `second_judge_backend` | `str` | Second judge backend | `"ollama"` |
| `disagreement_policy` | `str` | `"review"` (exit 3) or `"max"` | `"review"` |
| `on_review` | `str` | `"fail"` (exit 3) or `"warn"` (exit 0) | `"fail"` |
| `api_key_env` | `str` | Environment variable name for API key | `"OPENAI_API_KEY"` |
| `max_rpm` | `int` | Request throttle limit | `None` |
| `host` | `str` | Ollama daemon host URL | `"http://localhost:11434"` |
| `timeout` | `float`| Request timeout in seconds | `120.0` |
| `judge_retries` | `int` | Retries on unparseable judge replies | `2` |
| `judge_votes` | `int` | Self-consistency voting samples | `1` |
| `repeats` | `int` | Repetitions per attack | `1` |
| `seed` | `int` | Random seed for deterministic inference | `None` |
| `auto_patch` | `bool` | Enable automated prompt repair | `false` |
| `apply` | `bool` | Apply verified hardened prompt in-place | `false` |
| `fail_on_suspicious` | `bool` | Exit 1 if score >= 1 | `false` |
| `fail_on_format` | `bool` | Exit 1 if format validation fails | `false` |
| `auto_canary` | `bool` | Inject random cryptographic canary | `true` |
| `overlap_check` | `bool` | Fuzzy n-gram system prompt leak check | `true` |
| `overlap_threshold` | `float` | Overlap threshold for review escalation | `0.25` |
| `judge_cache` | `str` | Directory for judge response caching | `None` |
| `packs` | `list[str]` | Built-in attack packs to merge | `[]` |
| `min_severity` | `str` | Filter attacks by severity (`"low"`, etc.)| `"low"` |
| `report_json` | `str` | Path to export JSON audit report | `None` |

---

## Preset Configurations

Generate initial configuration files using `guard-rail-edge init --preset <name>`:

### 1. Hosted Groq Preset (`--preset groq`)
Recommended for fast, calibrated evaluation using Groq's free tier:

```toml
# guard-rail-edge.toml (Groq preset)
target_backend = "groq"
model = "openai/gpt-oss-20b"

judge_backend = "groq"
judge_model = "qwen/qwen3.8-27b"

api_key_env = "GROQ_API_KEY"
on_review = "fail"
packs = ["all"]
min_severity = "low"
report_json = "ci_report.json"
```

### 2. Local Ollama Preset (`--preset ollama`)
For entirely offline, on-premise execution:

```toml
# guard-rail-edge.toml (Ollama preset)
target_backend = "ollama"
model = "llama3.2:3b"

judge_backend = "ollama"
judge_model = "qwen2.5:7b"
host = "http://localhost:11434"

# Note: small local judges may miss subtle prompt extraction leaks.
# Run `guard-rail-edge calibrate` to verify your judge.
on_review = "fail"
packs = ["all"]
```

### 3. Offline Mock Preset (`--preset mock`)
For lightweight unit tests and CI runners without GPU or external credentials:

```toml
# guard-rail-edge.toml (Mock preset)
mock = true
packs = ["system_prompt_leakage"]
on_review = "fail"
report_json = "ci_report.json"
```

---

## Configuration via `pyproject.toml`

For Python projects, define settings inside `pyproject.toml`:

```toml
[tool.guard-rail-edge]
judge_backend = "groq"
judge_model = "qwen/qwen3.8-27b"
api_key_env = "GROQ_API_KEY"
on_review = "fail"
auto_canary = true
report_json = "reports/security_audit.json"
```

