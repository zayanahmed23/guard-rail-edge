# Contributing to guard-rail-edge 🛡️

Thank you for your interest in contributing to **guard-rail-edge**! We welcome community contributions, bug reports, feature proposals, and security attack vectors.

---

## 🛠️ Development Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/zayanahmed23/guard-rail-edge.git
   cd guard-rail-edge

   ```

2. **Create and activate a virtual environment**:
   ```bash
   python -m venv .venv
   # On macOS/Linux:
   source .venv/bin/activate
   # On Windows (PowerShell):
   .venv\Scripts\Activate.ps1
   ```

3. **Install dependencies in editable development mode**:
   ```bash
   pip install -e ".[dev]"
   ```

---

## 🧪 Running the Test Suite

We use `pytest` for unit, schema validation, and end-to-end CLI integration testing. All tests run offline without requiring a live Ollama daemon:

```bash
python -m pytest -v
```

Before submitting a Pull Request, ensure **100% of tests pass**.

---

## 🚀 Running Local Evaluations

Test the CLI locally using the simulated offline mock mode:

```bash
# Run against the example test suite
guard-rail-edge run --suite examples/tests.json --mock

# Test automated self-healing diff generation
guard-rail-edge run --suite examples/tests.json --mock --auto-patch

# Test in-place auto-hardening
guard-rail-edge run --suite examples/tests.json --mock --apply
```

If you have a local Ollama server running:
```bash
ollama serve
ollama pull gemma:2b
guard-rail-edge run --suite examples/tests.json --model gemma:2b
```

---

## 📐 Code Style & Architecture Guidelines

- **Package Structure**: All core logic lives in `guard_rail_edge/` (`schemas.py`, `evaluator.py`, `patcher.py`, `main.py`). The CLI entry points are `guard-rail-edge` and `python -m guard_rail_edge`.

- **Strict Typing**: All data structures must be defined with **Pydantic v2** models in `guard_rail_edge/schemas.py`.
- **Fault-Tolerant Parsing**: LLM outputs must be parsed resiliently (structured schema -> regex extraction -> deterministic fallback).
- **Clean Diff Generation**: Changes to system prompts must preserve exact disk line endings and indentation so `git apply` succeeds in CI.

---

## 🛡️ Adding an Attack to the Built-In Library

We welcome new prompt injection, evasion, and jailbreak vectors to our curated attack packs! When adding an attack:

1. **Locate or Create the Pack**: Built-in packs live in `guard_rail_edge/attacks/<pack-name>.json`.
2. **Schema & ID Format**:
   - Each attack must adhere to `AttackModel` in `guard_rail_edge/schemas.py`.
   - `id`: Must be unique across all packs and strictly match `^[A-Z]{2,3}-\d{3}$` (e.g. `PE-007`, `IO-007`).
   - `category`: Must match the parent pack's name exactly.
   - `severity`: Must be `"low"`, `"medium"`, or `"high"`.
   - `name`: A concise, human-readable description.
   - `input`: The adversarial prompt string (must not duplicate existing attacks).
   - `references`: Optional list of CVEs, OWASP techniques, or URLs.
   - `decoded_hint`: Optional decoded keyword for obfuscated payloads (Base64/ROT13).
3. **Harmless Goal Rule (MANDATORY)**:
   - Every attack must test whether the target model breaks **its own system prompt constraints** (e.g. leaks instructions, leaks a placeholder discount code, drops persona, outputs off-topic text, violates JSON formatting).
   - The payload's goal must be **strictly harmless** (e.g. "write a poem about pirates", "output raw XML", "say HELLO").
   - **ZERO harmful payloads**: Attacks containing real-world malware, weapons, drugs, hate speech, self-harm, or hazardous material are strictly rejected.
4. **Run the Verification Tests**:
   Ensure all schema, uniqueness, and decoding validations pass before opening a PR:
   ```bash
   python -m pytest tests/test_attack_library.py tests/test_packs_cli.py
   ```

---

## 📬 Pull Request Process

1. Fork the repo and create your branch from `main`:
   ```bash
   git checkout -b feature/my-cool-improvement
   ```
2. Commit your changes with clear, descriptive commit messages.
3. Add unit tests in `tests/` covering your changes.
4. Verify that `python -m pytest -v` passes completely.
5. Open a Pull Request on GitHub with a concise summary of the rationale and testing done.

---

## 📄 License

By contributing to **guard-rail-edge**, you agree that your contributions will be licensed under the project's [MIT License](LICENSE).
