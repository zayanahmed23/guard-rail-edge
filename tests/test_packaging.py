"""Tests for packaging, wheel contents, and --version flag."""

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from guard_rail_edge import __version__
from guard_rail_edge.main import app

runner = CliRunner(env={"COLUMNS": "200", "NO_COLOR": "1"})


def test_cli_version_flag_via_runner():
    """guard-rail-edge --version via CliRunner prints the version."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_cli_version_flag_via_run_subcommand():
    """guard-rail-edge run --version prints the version."""
    result = runner.invoke(app, ["run", "--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_python_module_version_flag():
    """python -m guard_rail_edge --version exits 0 and prints the version."""
    result = subprocess.run(
        [sys.executable, "-m", "guard_rail_edge", "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert __version__ in result.stdout


@pytest.mark.slow
def test_wheel_contains_only_package_files(tmp_path: Path):
    """Build a wheel in an isolated directory and assert every file (excluding *.dist-info/) starts with 'guard_rail_edge/'."""
    import importlib.util
    import shutil

    if not importlib.util.find_spec("build"):
        pytest.skip("build module not installed in test environment")

    repo_root = Path(__file__).parent.parent
    src_dir = tmp_path / "src"
    out_dir = tmp_path / "dist"

    def ignore_patterns(path: str, names: list[str]) -> set[str]:
        ignored = set()
        for name in names:
            if name in (
                ".git",
                "build",
                "dist",
                ".venv",
                "venv",
                "env",
                "__pycache__",
                ".pytest_cache",
                ".mypy_cache",
                ".ruff_cache",
            ):
                ignored.add(name)
            elif name.endswith(".egg-info"):
                ignored.add(name)
        return ignored

    shutil.copytree(repo_root, src_dir, ignore=ignore_patterns)

    # Build wheel into out_dir from clean isolated source directory
    res = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(out_dir)],
        cwd=str(src_dir),
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        pytest.fail(f"Failed to build wheel:\nStdout: {res.stdout}\nStderr: {res.stderr}")

    wheel_files = list(out_dir.glob("*.whl"))
    assert len(wheel_files) == 1, f"Expected 1 wheel, found: {wheel_files}"

    with zipfile.ZipFile(wheel_files[0], "r") as z:
        names = z.namelist()

    # Filter out dist-info files
    non_dist_info = [n for n in names if ".dist-info/" not in n and not n.endswith(".dist-info")]

    for name in non_dist_info:
        assert name.startswith("guard_rail_edge/"), (
            f"Found top-level module or file '{name}' in wheel outside 'guard_rail_edge/' package"
        )


def test_version_is_0_5_2():
    """Assert package version is bumped to 0.5.2."""
    assert __version__ == "0.5.2"


def test_pyproject_metadata():
    """Assert pyproject.toml contains required keywords, classifiers, and project URLs."""
    import tomllib

    pyproject_path = Path("pyproject.toml")
    assert pyproject_path.is_file()
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    project = data.get("project", {})
    keywords = project.get("keywords", [])
    expected_keywords = [
        "prompt-injection",
        "red-teaming",
        "llm-security",
        "jailbreak",
        "edge-ai",
        "ollama",
        "groq",
    ]
    for kw in expected_keywords:
        assert kw in keywords, f"Missing keyword '{kw}' in pyproject.toml"

    classifiers = project.get("classifiers", [])
    assert "Framework :: Pytest" in classifiers
    assert "Intended Audience :: Developers" in classifiers
    assert "Intended Audience :: Science/Research" in classifiers
    assert "Topic :: Security" in classifiers

    urls = project.get("urls", {})
    for url_key in ["Homepage", "Repository", "Issues", "Documentation", "Changelog"]:
        assert url_key in urls, f"Missing URL '{url_key}' in pyproject.toml"


def test_launch_hygiene_files_exist():
    """Assert all required launch hygiene and community health files exist."""
    required_files = [
        "SECURITY.md",
        "CODE_OF_CONDUCT.md",
        "CITATION.cff",
        ".github/ISSUE_TEMPLATE/bug_report.md",
        ".github/ISSUE_TEMPLATE/feature_request.md",
        ".github/ISSUE_TEMPLATE/new_attack.md",
        ".github/PULL_REQUEST_TEMPLATE.md",
    ]
    for rel_path in required_files:
        p = Path(rel_path)
        assert p.is_file(), f"Missing required file: {rel_path}"
        assert p.stat().st_size > 0, f"File is empty: {rel_path}"
