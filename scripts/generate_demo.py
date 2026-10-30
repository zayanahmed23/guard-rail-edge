"""Generate realistic terminal demo SVG using Rich console recording."""

from pathlib import Path

from typer.testing import CliRunner

from guard_rail_edge.cli import app
from guard_rail_edge.render import console


def generate_demo_svg(output_path: Path) -> None:
    """Run simulated run and calibration, saving terminal output to SVG."""
    orig_record = console.record
    orig_width = console._width

    try:
        console.record = True
        console._width = 110

        # Step 1: Run adversarial security evaluation
        console.print("[bold cyan]$ guard-rail-edge run examples/support-bot/tests.json --mock[/bold cyan]")
        runner = CliRunner()
        runner.invoke(app, ["run", "--mock", "examples/support-bot/tests.json"])

        # Step 2: Run benchmark calibration checks
        console.print("\n[bold cyan]$ guard-rail-edge calibrate --checks-only[/bold cyan]")
        runner.invoke(app, ["calibrate", "--checks-only"])

        output_path.parent.mkdir(parents=True, exist_ok=True)
        svg_content = console.export_svg(title="guard-rail-edge: Prompt-Injection Evaluation & Judge Calibration")
        output_path.write_text(svg_content, encoding="utf-8")
    finally:
        console.record = orig_record
        console._width = orig_width
        if hasattr(console, "_record_buffer"):
            console._record_buffer.clear()


if __name__ == "__main__":
    out_svg = Path("assets/demo.svg")
    generate_demo_svg(out_svg)
    print(f"Generated demo at {out_svg} ({out_svg.stat().st_size} bytes)")
