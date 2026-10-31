# Official GitHub Action: `guard-rail-edge`

The `guard-rail-edge` GitHub Action integrates automated prompt injection testing, canary tracking, and defense-in-depth evaluations directly into your CI/CD pipeline.

---

## ⚡ Quick Start

Add this step to your GitHub Actions workflow (`.github/workflows/security.yml`):

```yaml
name: Prompt Injection Security Gate

on:
  push:
    branches: [main]
  pull_request:

jobs:
  guardrail-test:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Run Guardrail Security Gate
        uses: zayanahmed23/guard-rail-edge@v0.5.1
        with:
          suite: tests.json
        env:
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
```

---

## ⚙️ Inputs Reference

| Input | Description | Required | Default |
|---|---|:---:|---|
| `suite` | Path to the JSON test suite file | No | `tests.json` |
| `config` | Path to custom configuration file (`guard-rail-edge.toml` or `pyproject.toml`) | No | `""` (auto-discovered) |
| `judge-backend` | Evaluator backend: `ollama` or `groq` | No | `""` (defaults to tool config) |
| `judge-model` | Evaluator judge model name (e.g. `qwen/qwen3.8-27b`) | No | `""` (defaults to tool config) |
| `on-review` | Action policy for `NEEDS REVIEW` verdicts: `fail` (exit 3) or `warn` (exit 0) | No | `fail` |
| `python-version` | Python runtime version to initialize | No | `3.12` |
| `version` | Package version of `guard-rail-edge` to install (`0.5.1` or `local`) | No | `0.5.1` |
| `report-path` | Destination filepath for machine-readable JSON evaluation report | No | `.guard-rail-edge-report.json` |
| `artifact-name` | Name of the report artifact to upload | No | `guard-rail-edge-report` |
| `extra-args` | Additional command-line flags passed directly to `guard-rail-edge run` | No | `""` |

---

## 🔐 Secrets Configuration

Set secrets in **Repository Settings -> Secrets and variables -> Actions**:

| Secret Name | Provider / Purpose |
|---|---|
| `GROQ_API_KEY` | Recommended free-tier hosted judge (`qwen/qwen3.8-27b`) |
| `OPENAI_API_KEY` | OpenAI or compatible API endpoints |
| `OPENROUTER_API_KEY` | OpenRouter multi-model router |
| `GEMINI_API_KEY` | Google Gemini API endpoints |

*Note: `guard-rail-edge` never logs or leaks secret values. All API credentials are read directly from process environment variables.*

---

## 🚀 Common Workflow Patterns

### 1. Hosted Groq Evaluation (Recommended)

Uses free-tier Groq API for sub-minute evaluation with our calibrated trustworthy judge:

```yaml
- name: Evaluate System Prompt Defenses
  uses: zayanahmed23/guard-rail-edge@v0.5.1
  with:
    suite: prompts/customer-service/tests.json
    judge-backend: groq
    judge-model: qwen/qwen3.8-27b
  env:
    GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
```

### 2. Self-Hosted Ollama Runner

Evaluate locally without sending prompts to third-party APIs:

```yaml
- name: Start Ollama Daemon
  run: |
    curl -fsSL https://ollama.com/install.sh | sh
    ollama serve &
    sleep 3
    ollama pull qwen2.5:7b

- name: Run On-Prem Guardrail Gate
  uses: zayanahmed23/guard-rail-edge@v0.5.1
  with:
    suite: tests.json
    judge-backend: ollama
    judge-model: qwen2.5:7b
    extra-args: "--host http://localhost:11434"
```

### 3. Automated Self-Healing Patch PR

Generate a hardened prompt `.patch` file and create an automated Pull Request when vulnerabilities are detected:

```yaml
- name: Run Evaluation with Auto-Patch
  id: guardrail
  uses: zayanahmed23/guard-rail-edge@v0.5.1
  continue-on-error: true
  with:
    suite: tests.json
    extra-args: "--auto-patch"
  env:
    GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}

- name: Create Hardening Pull Request
  if: steps.guardrail.outcome == 'failure' && hashFiles('*.patch') != ''
  uses: peter-evans/create-pull-request@v6
  with:
    title: "chore(security): self-healing system prompt hardening patch"
    commit-message: "chore(security): apply guard-rail-edge hardening patch"
    branch: "guardrail-auto-patch"
    body: "Automated prompt injection vulnerability detected by guard-rail-edge. Applied self-healing prompt defense boundary."
```

### 4. Monorepos with Multiple LLM Services

Run evaluations across distinct subdirectories using matrix strategies:

```yaml
jobs:
  evaluate-services:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        service: [support-bot, internal-hr-bot, rag-assistant]
    steps:
      - uses: actions/checkout@v4
      - uses: zayanahmed23/guard-rail-edge@v0.5.1
        with:
          suite: examples/${{ matrix.service }}/tests.json
          report-path: reports/${{ matrix.service }}-report.json
        env:
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
```

---

## 📋 Deterministic Exit Codes

The GitHub Action surfaces the exact exit code of `guard-rail-edge run`:

| Exit Code | Classification | Meaning | Action Step Result |
|:---:|---|---|:---:|
| **`0`** | **PASSED** | All adversarial prompts were safely refused or handled. | ✅ Succeeded |
| **`1`** | **BLOCKED** | Vulnerability, jailbreak, or prompt leak detected. | ❌ Failed |
| **`2`** | **ERROR** | Configuration error, invalid suite syntax, or connection failure. | ❌ Failed |
| **`3`** | **NEEDS REVIEW** | Non-unanimous judge disagreement or high overlap detected (under `--on-review fail`). | ❌ Failed |

---

## 📦 Artifacts & Job Summaries

Every workflow run automatically attaches:
- **`guard-rail-edge-report`**: The machine-readable evaluation report JSON containing full test traces, metrics, confusion matrices, and canaries.
- **`guard-rail-edge-patch`**: Unified `.patch` diff when `--auto-patch` synthesizes a hardened system prompt.
- **GitHub Step Summary**: A rich Markdown dashboard embedded in the job run details displaying total test counts, verdicts, and detected security findings.

