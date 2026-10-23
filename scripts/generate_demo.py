"""Generate high-resolution SVG terminal recording for README showcase."""

import sys
from pathlib import Path
from rich.console import Console

import guard_rail_edge.main as cli_main


def generate_svg() -> None:
    assets_dir = Path("assets")
    assets_dir.mkdir(parents=True, exist_ok=True)
    svg_path = assets_dir / "demo.svg"

    # Create recording console with fixed width=100 for crisp GitHub presentation
    rec_console = Console(record=True, width=100, force_terminal=True, color_system="truecolor")
    cli_main.console = rec_console

    # Run evaluation against examples/tests.json in mock mode with auto-patch
    try:
        cli_main.run(
            suite=Path("examples/tests.json"),
            model="gemma:2b",
            host="http://localhost:11434",
            auto_patch=True,
            apply=False,
            patch_output=Path("examples/tests.patch"),
            verify_patch=True,
            fail_on_suspicious=False,
            report_json=None,
            mock=True,
        )
    except SystemExit:
        pass

    # Export recorded output to SVG
    rec_console.save_svg(
        str(svg_path),
        title="guard-rail-edge — Automated Prompt Red-Teaming & Self-Healing",
    )
    print(f"Generated demo SVG at {svg_path} (size: {svg_path.stat().st_size} bytes)")



if __name__ == "__main__":
    generate_svg()
