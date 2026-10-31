# guard-rail-edge 🛡️

**Prompt-injection testing for CI/CD that measures whether its own AI judge can be trusted.**

[![PyPI version](https://img.shields.io/pypi/v/guard-rail-edge?color=blue&style=flat-square)](https://pypi.org/project/guard-rail-edge/)
[![Python 3.11 | 3.12 | 3.13](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg?style=flat-square)](https://www.python.org/downloads/)
[![CI & Tests](https://img.shields.io/github/actions/workflow/status/zayanahmed23/guard-rail-edge/ci.yml?branch=main&label=CI%20%26%20Tests&style=flat-square)](https://github.com/zayanahmed23/guard-rail-edge/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)
[![Calibrated Judge](https://img.shields.io/badge/Judge-Empirically%20Calibrated-success.svg?style=flat-square)](docs/real-model-results.md)

---

![guard-rail-edge Terminal Demo](assets/demo.svg)

---

## The Problem: Uncalibrated Judges Fail Silently

Most LLM security testers trust an arbitrary AI judge to grade security tests. In our empirical testing across 50 benchmark cases, **small local judges miss 20–30% of system prompt leaks** when disclosures are framed politely, while other models hallucinate an 85% false alarm rate on benign inputs.

`guard-rail-edge` eliminates blind trust with defense-in-depth:
1. **Code-First Catches**: Deterministic cryptographic canaries and fuzzy system-prompt overlap detection catch leaks before invoking an LLM.
2. **Empirically Calibrated Judges**: Benchmarked against ground-truth datasets with 95% Wilson confidence intervals.
3. **"NEEDS REVIEW" Verdict**: When an LLM judge is uncertain, ambiguous, or discordant, it escalates to `NEEDS REVIEW` (exit 3) instead of guessing `PASS`.

---

## ⚡ Quickstart (Under 60 Seconds)

### Step 1: Install `guard-rail-edge`
```bash
pip install guard-rail-edge
```

### Step 2: Set your API Key (or use offline mock)
```bash
# Recommended free hosted judge: Groq
export GROQ_API_KEY="gsk_..."

# Or on Windows PowerShell:
# $env:GROQ_API_KEY="gsk_..."
```
*(No API key? Test offline immediately with `guard-rail-edge init --preset mock`.)*

### Step 3: Initialize and Run
```bash
guard-rail-edge init --preset groq
guard-rail-edge run
```

---

## What It Checks

`guard-rail-edge` evaluates production prompt defenses across real-world workloads:

- **Direct Prompt Injection**: Instruction overrides, delimiter breakouts, and persona hijacking.
- **Indirect RAG Injections**: Attacks embedded inside retrieved knowledge base context.
- **System Prompt Exfiltration**: Extracting confidential rules, internal credentials, or canary tokens.
- **Format Breakouts**: Breaking structured JSON/schema contracts or smuggling executable payloads.
- **Roleplay & Social Engineering**: Authority emulation (e.g. fake compliance auditor) and hypothetical framing.

Explore realistic runnable suites in [`examples/`](examples/):
- [`examples/support-bot/`](examples/support-bot/): Customer support bot with confidential discount codes and canaries.
- [`examples/rag-assistant/`](examples/rag-assistant/): Internal Q&A assistant tested against indirect document injection.
- [`examples/internal-hr-bot/`](examples/internal-hr-bot/): Slack HR bot tested against compensation and executive leak probes.
- [`examples/json-api-agent/`](examples/json-api-agent/): Structured API agent enforcing strict JSON contracts.

---

## Calibrated Judge Accuracy

![Judge Calibration Chart](assets/judge-calibration.svg)

Empirical calibration benchmark results evaluated across 50 ground-truth cases (30 dev, 20 holdout):

<!-- BEGIN GENERATED CALIBRATION TABLE -->
| Status | Judge Model | Leak Detection Rate (95% CI) | False Alarm Rate (95% CI) | Calibration Verdict |
|---|---|:---:|:---:|---|
| **Passed** | Groq `qwen/qwen3.8-27b` | **100.0%** [83.9%, 100.0%] | **0.0%** [0.0%, 16.1%] | **TRUSTWORTHY** (Passed calibration) |
| **Passed** | Groq `openai/gpt-oss-120b` | **100.0%** [83.9%, 100.0%] | **35.0%** [18.1%, 56.7%] | **TRUSTWORTHY** (Passed calibration) |
| **Failed** | Local `qwen2.5:7b`* | **80.0%** [58.4%, 91.9%] | **0.0%** [0.0%, 16.1%] | **NOT TRUSTWORTHY** (Did not pass calibration) |
| **Failed** | Local `qwen2.5:0.5b`* | **90.0%** [69.9%, 97.2%] | **85.0%** [64.0%, 94.8%] | **NOT TRUSTWORTHY** (Did not pass calibration) |
| **Failed** | Local `gemma:2b`* | **10.0%** [2.8%, 30.1%] | **80.0%** [58.4%, 91.9%] | **NOT TRUSTWORTHY** (Did not pass calibration) |

*\*Evaluated in commit 101a81e on local CPU. Legacy results; see docs/real-model-results.md for raw details.*
*Calibration uses 50 cases (20 holdout, 8 holdout leaks); treat results as indicative, not a guarantee. Re-run `calibrate` on your own judge and, ideally, your own labelled cases.*
<!-- END GENERATED CALIBRATION TABLE -->

*Full evaluation methodology, confusion matrices, and audit logs: [docs/real-model-results.md](docs/real-model-results.md).*

---

## CI/CD Pipeline Integration

Add `guard-rail-edge` directly to your GitHub Actions workflow using our official composite action:

```yaml
- name: Run Guardrail Security Gate
  uses: zayanahmed23/guard-rail-edge@v0.5.1
  with:
    suite: tests.json
    on-review: fail
  env:
    GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
```

*(Or run via manual CLI script: `pip install guard-rail-edge && guard-rail-edge doctor && guard-rail-edge run --on-review fail --report-json security-audit.json`.)*

### Deterministic Exit Codes
- **`0`**: **PASSED** — All adversarial tests verified safe.
- **`1`** : **BLOCKED** — Vulnerability or prompt leakage detected.
- **`2`**: **ERROR** — Configuration or operational runtime failure.
- **`3`**: **NEEDS REVIEW** — Evaluation uncertain; human review required.

---

## Comparison: When to Use Which

| Tool | Focus & Philosophy | When to Prefer |
|---|---|---|
| **`guard-rail-edge`** | **Calibrated prompt-injection CI gate** with code-first canary & overlap detection, self-healing patches, and "needs-review" verdicts. | When you need an automated, fast CI/CD security gate that measures whether its own evaluator can be trusted. |
| [**promptfoo**](https://www.promptfoo.dev/) | General LLM evaluation framework for output quality, regression assertions, and wide custom plugins. | When running multi-dimensional model evals, latency benchmarks, or prompt quality comparisons. |
| [**garak**](https://github.com/leondz/garak) | Deep, extensive LLM vulnerability scanner probing model-level security weaknesses. | When conducting exhaustive, academic-grade vulnerability assessments across thousands of generative probes. |
| [**PyRIT**](https://github.com/Azure/PyRIT) | Microsoft's red-teaming framework for multi-turn risk assessment and complex attack orchestration. | When evaluating multi-turn conversational agents, strategy graphs, and multimodal attack surfaces. |
| [**DeepTeam**](https://github.com/confident-ai/deepteam) | Enterprise red-teaming platform with web dashboards, risk metrics, and team management. | When looking for managed enterprise attack simulation and organizational compliance dashboards. |

---

## Documentation

- 🚀 [GitHub Action](docs/github-action.md) — Official composite action, step summaries, and PR automation.
- 📖 [CLI Reference](docs/cli-reference.md) — Complete options, flags, and command reference.
- ⚙️ [Configuration Guide](docs/configuration.md) — TOML files, pyproject.toml integration, and presets.
- 🎯 [Attack Library](docs/attack-library.md) — Attack packs, categories, and test schema.
- 🔬 [Judge Calibration](docs/calibration.md) — Methodology, 50-case benchmark, and Wilson score formulation.
- 🔌 [Backends & Caching](docs/backends.md) — Local Ollama, Groq, OpenAI endpoints, and cache setup.
- 📊 [Real Model Results](docs/real-model-results.md) — Empirical benchmark tables and proofs.

---

## License

Distributed under the [MIT License](LICENSE).
