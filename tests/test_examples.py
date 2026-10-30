"""Tests verifying the realistic example suites under examples/."""

import json
import tomllib
from pathlib import Path

from typer.testing import CliRunner

from guard_rail_edge.cli import app
from guard_rail_edge.schemas import TestSuite

EXAMPLE_DIRS = [
    "support-bot",
    "rag-assistant",
    "internal-hr-bot",
    "json-api-agent",
]


def test_example_suites_validation() -> None:
    """Assert all 4 example suites parse with TestSuite.model_validate and have >= 3 tests."""
    examples_root = Path("examples")
    assert examples_root.is_dir()

    for dir_name in EXAMPLE_DIRS:
        example_dir = examples_root / dir_name
        assert example_dir.is_dir(), f"Missing directory: {example_dir}"

        # Check README.md
        readme_path = example_dir / "README.md"
        assert readme_path.is_file(), f"Missing README: {readme_path}"
        readme_lines = readme_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(readme_lines) >= 3, f"README too short in {dir_name}"

        # Check guard-rail-edge.toml
        toml_path = example_dir / "guard-rail-edge.toml"
        assert toml_path.is_file(), f"Missing config: {toml_path}"
        toml_data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        assert isinstance(toml_data, dict)

        # Check tests.json
        tests_path = example_dir / "tests.json"
        assert tests_path.is_file(), f"Missing tests.json: {tests_path}"
        raw_json = json.loads(tests_path.read_text(encoding="utf-8"))
        suite = TestSuite.model_validate(raw_json)
        assert len(suite.tests) >= 3, f"Suite {dir_name} has fewer than 3 tests ({len(suite.tests)})"


def test_example_suites_run_in_mock_mode() -> None:
    """Assert all 4 example suites execute cleanly in --mock mode without unhandled errors."""
    runner = CliRunner()
    examples_root = Path("examples")

    for dir_name in EXAMPLE_DIRS:
        example_dir = examples_root / dir_name
        tests_path = str(example_dir / "tests.json")
        toml_path = str(example_dir / "guard-rail-edge.toml")

        result = runner.invoke(app, ["run", "--mock", "--config", toml_path, tests_path])
        # In mock mode, exit code should be 0 (all pass) or 1 (security score failure / fail-closed)
        # It must never crash (exit code 2 or uncaught exception).
        assert result.exit_code in (0, 1), f"Run crashed on {dir_name} with exit code {result.exit_code}:\n{result.stdout}"
