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

- **Package Structure**: All core logic lives in `guard_rail_edge/` (`schemas.py`, `evaluator.py`, `patcher.py`, `main.py`). The root Python files (`main.py`, etc.) are minimal re-export shims.
- **Strict Typing**: All data structures must be defined with **Pydantic v2** models in `guard_rail_edge/schemas.py`.
- **Fault-Tolerant Parsing**: LLM outputs must be parsed resiliently (structured schema -> regex extraction -> deterministic fallback).
- **Clean Diff Generation**: Changes to system prompts must preserve exact disk line endings and indentation so `git apply` succeeds in CI.

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
