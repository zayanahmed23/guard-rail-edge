"""Tests for packaging, wheel contents, and --version flag."""

import subprocess
import sys
import zipfile

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


def test_wheel_contains_only_package_files(tmp_path):
    """Build a wheel and assert every file (excluding *.dist-info/) starts with 'guard_rail_edge/'."""
    import importlib.util
    if not importlib.util.find_spec("build"):
        pytest.skip("build module not installed in test environment")

    # Build wheel into tmp_path
    res = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        pytest.fail(f"Failed to build wheel:\nStdout: {res.stdout}\nStderr: {res.stderr}")

    wheel_files = list(tmp_path.glob("*.whl"))
    assert len(wheel_files) == 1, f"Expected 1 wheel, found: {wheel_files}"

    with zipfile.ZipFile(wheel_files[0], "r") as z:
        names = z.namelist()

    # Filter out dist-info files
    non_dist_info = [n for n in names if ".dist-info/" not in n and not n.endswith(".dist-info")]

    for name in non_dist_info:
        assert name.startswith("guard_rail_edge/"), (
            f"Found top-level module or file '{name}' in wheel outside 'guard_rail_edge/' package"
        )
