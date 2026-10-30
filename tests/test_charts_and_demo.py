"""Tests verifying judge calibration chart generation and terminal demo recording."""

import json
from pathlib import Path

from scripts.generate_demo import generate_demo_svg
from scripts.make_charts import generate_judge_calibration_svg


def test_make_charts_generation(tmp_path: Path) -> None:
    """Assert make_charts generates valid SVG and matches docs/data/judge_calibration.json."""
    data_path = Path("docs/data/judge_calibration.json")
    assert data_path.is_file(), f"Missing calibration data: {data_path}"

    out_svg = tmp_path / "chart.svg"
    generate_judge_calibration_svg(data_path, out_svg)

    assert out_svg.is_file()
    content = out_svg.read_text(encoding="utf-8")
    assert content.startswith("<svg") or "<svg" in content
    assert "</svg>" in content
    assert "Judge Calibration" in content
    assert out_svg.stat().st_size > 5000


def test_judge_calibration_data_matches_markdown() -> None:
    """Assert docs/data/judge_calibration.json numbers are consistent with docs/real-model-results.md."""
    data_path = Path("docs/data/judge_calibration.json")
    results_path = Path("docs/real-model-results.md")

    models_data = json.loads(data_path.read_text(encoding="utf-8"))
    results_text = results_path.read_text(encoding="utf-8")

    for item in models_data:
        model_name = item["model"]
        # Assert model is mentioned in the benchmark table
        assert model_name in results_text, f"Model {model_name} missing from docs/real-model-results.md"
        # Format percentages as shown in table (e.g. 100.0%, 80.0%, 5.0%)
        leak_pct = f"{item['leak_detection_rate'] * 100:.1f}%"
        fa_pct = f"{item['false_alarm_rate'] * 100:.1f}%"
        assert leak_pct in results_text, f"Leak rate {leak_pct} for {model_name} not found in docs"
        assert fa_pct in results_text, f"False alarm rate {fa_pct} for {model_name} not found in docs"


def test_generate_demo_output(tmp_path: Path) -> None:
    """Assert generate_demo creates a terminal SVG larger than 10KB."""
    demo_svg = tmp_path / "demo.svg"
    generate_demo_svg(demo_svg)

    assert demo_svg.is_file()
    assert demo_svg.stat().st_size > 10000
    content = demo_svg.read_text(encoding="utf-8")
    assert "<svg" in content
    assert "</svg>" in content
