# Execution Backends & Caching

`guard-rail-edge` supports both local execution via [Ollama](https://ollama.ai/) and cloud-hosted inference via OpenAI-compatible endpoints, allowing complete flexibility between zero-cost privacy and high-capacity frontier model grading.

## Supported Backends

### 1. Ollama (Local & On-Premise)
- **Target / Judge Backend**: `ollama`
- **Default Host**: `http://localhost:11434`
- **Privacy & Security**: All inference runs entirely within your machine or private runner. Zero data leaves your perimeter.
- **Hardware Profile**: Small models (`llama3.2:3b`, `qwen2.5:7b`) run on modern CPUs or consumer GPUs.

```bash
guard-rail-edge run --model llama3.2:3b --judge-model qwen2.5:7b
```

---

### 2. Groq (Free Tier / Ultra-Fast Inference)
- **Target / Judge Backend**: `groq`
- **Base URL**: `https://api.groq.com/openai/v1`
- **Recommended Judge**: `qwen/qwen3.8-27b`
- **Key Configuration**: Pass key variable name via `--api-key-env GROQ_API_KEY`. Never hardcode secrets.

```bash
guard-rail-edge run --target-backend groq --model llama-3.1-8b-instant \
  --judge-backend groq --judge-model qwen/qwen3.8-27b \
  --api-key-env GROQ_API_KEY
```

---

### 3. OpenAI-Compatible & Self-Hosted Providers
Connect to vLLM, OpenRouter, Together AI, or corporate proxy gateways:

```bash
guard-rail-edge run \
  --target-backend openai \
  --target-base-url https://openrouter.ai/api/v1 \
  --model anthropic/claude-3.5-sonnet \
  --api-key-env OPENROUTER_API_KEY
```

---

## Rate-Limit Management & Exponential Backoff

When evaluating large attack suites on hosted rate-limited providers, `guard-rail-edge` automatically manages throttling:
- Configurable request throttling: `--max-rpm <N>`.
- Automatic exponential backoff with jitter on HTTP `429` (Too Many Requests) and `503` (Service Unavailable).
- Diagnostic counters track and display rate-limit delays in final reports.

---

## Judge Response Caching

To prevent redundant LLM inference during prompt iterations and configuration tuning, `guard-rail-edge` includes disk-backed response caching:
- Cached by SHA-256 hash of system prompt, attack input, target output, and options.
- Enabled by default or via `--judge-cache <DIR>` (`.guard-rail-edge-cache/`).
- Force fresh evaluations with `--no-cache`.
- Only valid, parseable judge verdicts are cached; errors are never persisted.

---

## Privacy Note on Free Hosted Tiers

Free hosted API tiers (such as free provider endpoints) may retain prompt data for monitoring or model training. When testing sensitive internal intellectual property, production secrets, or proprietary system instructions, use local Ollama models or private, enterprise-tier OpenAI endpoints.

