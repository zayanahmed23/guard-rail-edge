## Summary of Changes

Describe what this PR accomplishes and why.

## Pull Request Checklist

Please ensure your contribution satisfies all quality gates before requesting review:

- [ ] **Tests pass**: `pytest --cov=guard_rail_edge --cov-fail-under=85` passes cleanly.
- [ ] **Code coverage**: Maintained at $\ge 85\%$.
- [ ] **Linting & Formatting**: `ruff check .` reports no errors.
- [ ] **Type Checking**: `mypy guard_rail_edge` reports no issues.
- [ ] **Module Size**: No Python file exceeds 450 lines.
- [ ] **Documentation**: Updated `docs/` or `README.md` if CLI flags or config options were altered.
- [ ] **Zero Credentials**: Confirmed no API keys, tokens, or confidential prompts are committed.
