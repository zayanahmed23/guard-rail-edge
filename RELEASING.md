# Release Process & PyPI Publishing Guide 🚀

This document outlines the release process for **`guard-rail-edge`**, automated via GitHub Actions using **PyPI Trusted Publishing** (OIDC, no long-lived API tokens).

---

## 🔑 One-Time Setup: PyPI Trusted Publishing

Before triggering the first release, configure PyPI Trusted Publishing:

### 1. PyPI (Production) Setup
1. Log in to [pypi.org](https://pypi.org/).
2. Navigate to **Account Settings** &rarr; **Publishing**.
3. Under **Add a new publisher**, select **GitHub**.
4. Configure the publisher:
   - **PyPI Project Name**: `guard-rail-edge`
   - **Owner**: `zayanahmed23`
   - **Repository name**: `guard-rail-edge`
   - **Workflow name**: `release.yml`
   - **Environment name**: `pypi`
5. Click **Add publisher**.

### 2. TestPyPI (Staging) Setup
1. Log in to [test.pypi.org](https://test.pypi.org/).
2. Navigate to **Account Settings** &rarr; **Publishing**.
3. Under **Add a new publisher**, select **GitHub**.
4. Configure the publisher:
   - **PyPI Project Name**: `guard-rail-edge`
   - **Owner**: `zayanahmed23`
   - **Repository name**: `guard-rail-edge`
   - **Workflow name**: `test-pypi.yml`
   - **Environment name**: `testpypi`
5. Click **Add publisher**.

### 3. GitHub Repository Environments
1. On GitHub, navigate to [Settings &rarr; Environments](https://github.com/zayanahmed23/guard-rail-edge/settings/environments).
2. Create environment `pypi` (optionally configure required reviewers for manual approval).
3. Create environment `testpypi`.

---

## 📦 Release Workflow

Follow these steps for every release:

### 1. Version Bump & Changelog
1. Update `__version__` in `guard_rail_edge/__init__.py`.
2. Add a new release section in `CHANGELOG.md` under `## [X.Y.Z] - YYYY-MM-DD`.

### 2. Local Verification Gate
Run the standard validation suite:
```bash
# Pytest & Coverage
python -m pytest -q --cov=guard_rail_edge --cov-fail-under=85

# Lint & Type Check
python -m ruff check .
python -m mypy guard_rail_edge

# Build & Twine Check
python -m build
python -m twine check dist/*
```

### 3. Commit & Push to Main
```bash
git add guard_rail_edge/__init__.py CHANGELOG.md
git commit -m "chore: prepare release vX.Y.Z"
git push origin main
```
Ensure CI passes on Python 3.11, 3.12, and 3.13.

### 4. Optional: Dry-Run on TestPyPI
1. Go to **Actions** &rarr; **TestPyPI Dry-Run Release**.
2. Click **Run workflow** on `main`.
3. Verify test installation:
   ```bash
   pip install --index-url https://test.pypi.org/simple/ --no-deps guard-rail-edge
   ```

### 5. Tag and Publish
Create and push the version tag:
```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

GitHub Actions will automatically:
1. Validate that the git tag matches `guard_rail_edge.__version__`.
2. Build the source distribution (`.tar.gz`) and wheel (`.whl`).
3. Publish packages to PyPI via OIDC Trusted Publishing.
4. Extract release notes from `CHANGELOG.md` and create a GitHub Release attaching the release assets.
