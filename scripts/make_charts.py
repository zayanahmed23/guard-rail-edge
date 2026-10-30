"""Generate judge calibration chart SVG from docs/data/judge_calibration.json."""

import json
from pathlib import Path


def generate_judge_calibration_svg(data_path: Path, output_path: Path) -> None:
    """Generate 1200x675 SVG chart illustrating judge calibration benchmarks."""
    models_data = json.loads(data_path.read_text(encoding="utf-8"))

    width = 1200
    height = 675
    chart_top = 135
    chart_bottom = 560
    chart_left = 90
    chart_right = 1110
    chart_height = chart_bottom - chart_top
    chart_width = chart_right - chart_left

    def y_pos(val: float) -> float:
        return chart_bottom - (val * chart_height)

    num_models = len(models_data)
    slot_width = chart_width / num_models

    svg_parts = []
    # Header & background
    svg_parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">'
    )
    svg_parts.append("""
  <defs>
    <style>
      .title { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; font-size: 23px; font-weight: 700; fill: #f0f6fc; }
      .subtitle { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; font-size: 15px; fill: #8b949e; }
      .footer { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; font-size: 13px; fill: #6e7681; }
      .axis-label { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; font-size: 12px; fill: #8b949e; text-anchor: end; }
      .model-name { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; font-size: 12px; font-weight: 600; fill: #e6edf3; text-anchor: middle; }
      .model-backend { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; font-size: 11px; fill: #7d8590; text-anchor: middle; }
      .badge-text { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; font-size: 10px; font-weight: 700; text-anchor: middle; }
      .legend-text { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; font-size: 12px; fill: #c9d1d9; }
      .bar-val { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; font-size: 10px; font-weight: 600; text-anchor: middle; }
    </style>
    <linearGradient id="bg-grad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#0d1117"/>
      <stop offset="100%" stop-color="#161b22"/>
    </linearGradient>
    <linearGradient id="pass-grad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#238636" stop-opacity="0.18"/>
      <stop offset="100%" stop-color="#238636" stop-opacity="0.04"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg-grad)"/>
  <rect x="1" y="1" width="1198" height="673" rx="8" fill="none" stroke="#30363d" stroke-width="1.5"/>
""")

    # Titles
    svg_parts.append(
        '  <text x="90" y="48" class="title">Judge Calibration: Leak Detection vs False Alarm Rate (50 cases)</text>'
    )
    svg_parts.append(
        '  <text x="90" y="74" class="subtitle">Only 2 of 8 models passed calibration. Small local models fail silently.</text>'
    )

    # Legend at top right
    svg_parts.append("""  <g id="legend">
    <rect x="710" y="36" width="16" height="12" rx="3" fill="#38bdf8"/>
    <text x="732" y="46" class="legend-text">Leak Detection Rate</text>

    <rect x="880" y="36" width="16" height="12" rx="3" fill="#f87171"/>
    <text x="902" y="46" class="legend-text">False Alarm Rate</text>

    <line x1="710" y1="68" x2="726" y2="68" stroke="#22c55e" stroke-width="2" stroke-dasharray="4,3"/>
    <text x="732" y="72" class="legend-text" fill="#22c55e">Min Catch (>=80%)</text>

    <line x1="880" y1="68" x2="896" y2="68" stroke="#ef4444" stroke-width="2" stroke-dasharray="4,3"/>
    <text x="902" y="72" class="legend-text">Max FA (<=15%)</text>
  </g>""")

    # Gridlines and y-axis labels
    for pct in [0, 20, 40, 60, 80, 100]:
        y = y_pos(pct / 100.0)
        svg_parts.append(
            f'  <line x1="{chart_left}" y1="{y:.1f}" x2="{chart_right}" y2="{y:.1f}" stroke="#21262d" stroke-width="1"/>'
        )
        svg_parts.append(f'  <text x="{chart_left - 12}" y="{y + 4:.1f}" class="axis-label">{pct}%</text>')

    # Threshold Lines
    y_80 = y_pos(0.80)
    y_15 = y_pos(0.15)
    svg_parts.append(
        f'  <line x1="{chart_left}" y1="{y_80:.1f}" x2="{chart_right}" y2="{y_80:.1f}" stroke="#22c55e" stroke-width="2" stroke-dasharray="6,4"/>'
    )
    svg_parts.append(
        f'  <text x="{chart_right + 8}" y="{y_80 + 4:.1f}" font-family="-apple-system, sans-serif" font-size="11" font-weight="600" fill="#22c55e">80% Target</text>'
    )

    svg_parts.append(
        f'  <line x1="{chart_left}" y1="{y_15:.1f}" x2="{chart_right}" y2="{y_15:.1f}" stroke="#ef4444" stroke-width="2" stroke-dasharray="6,4"/>'
    )
    svg_parts.append(
        f'  <text x="{chart_right + 8}" y="{y_15 + 4:.1f}" font-family="-apple-system, sans-serif" font-size="11" font-weight="600" fill="#ef4444">15% Max FA</text>'
    )

    # Bars and model groups
    bar_width = 30
    bar_gap = 6
    group_width = (bar_width * 2) + bar_gap

    for i, m in enumerate(models_data):
        x_center = chart_left + (i * slot_width) + (slot_width / 2.0)
        x_start = x_center - (group_width / 2.0)

        # Highlight box for passed models
        if m["passed"]:
            box_x = chart_left + (i * slot_width) + 4
            box_w = slot_width - 8
            svg_parts.append(
                f'  <rect x="{box_x:.1f}" y="{chart_top - 10:.1f}" width="{box_w:.1f}" height="{chart_height + 15:.1f}" rx="6" fill="url(#pass-grad)" stroke="#238636" stroke-width="1.2" stroke-dasharray="3,3"/>'
            )
            # Badge
            svg_parts.append(
                f'  <rect x="{x_center - 32:.1f}" y="{chart_top - 28:.1f}" width="64" height="17" rx="8" fill="#238636"/>'
            )
            svg_parts.append(
                f'  <text x="{x_center:.1f}" y="{chart_top - 16:.1f}" class="badge-text" fill="#ffffff">PASSED</text>'
            )

        # Bar 1: Leak Detection Rate
        leak_val = float(m["leak_detection_rate"])
        y_leak = y_pos(leak_val)
        h_leak = chart_bottom - y_leak
        x_leak = x_start
        svg_parts.append(
            f'  <rect x="{x_leak:.1f}" y="{y_leak:.1f}" width="{bar_width}" height="{h_leak:.1f}" rx="3" fill="#38bdf8"/>'
        )

        # Wilson CI for Bar 1
        y_ci_l1 = y_pos(float(m["leak_ci_lower"]))
        y_ci_u1 = y_pos(float(m["leak_ci_upper"]))
        x_mid1 = x_leak + (bar_width / 2.0)
        svg_parts.append(
            f'  <line x1="{x_mid1:.1f}" y1="{y_ci_u1:.1f}" x2="{x_mid1:.1f}" y2="{y_ci_l1:.1f}" stroke="#0369a1" stroke-width="2"/>'
        )
        svg_parts.append(
            f'  <line x1="{x_mid1 - 5:.1f}" y1="{y_ci_u1:.1f}" x2="{x_mid1 + 5:.1f}" y2="{y_ci_u1:.1f}" stroke="#0369a1" stroke-width="2"/>'
        )
        svg_parts.append(
            f'  <line x1="{x_mid1 - 5:.1f}" y1="{y_ci_l1:.1f}" x2="{x_mid1 + 5:.1f}" y2="{y_ci_l1:.1f}" stroke="#0369a1" stroke-width="2"/>'
        )

        # Bar 2: False Alarm Rate
        fa_val = float(m["false_alarm_rate"])
        y_fa = y_pos(fa_val)
        h_fa = chart_bottom - y_fa
        x_fa = x_start + bar_width + bar_gap
        svg_parts.append(
            f'  <rect x="{x_fa:.1f}" y="{y_fa:.1f}" width="{bar_width}" height="{h_fa:.1f}" rx="3" fill="#f87171"/>'
        )

        # Wilson CI for Bar 2
        y_ci_l2 = y_pos(float(m["fa_ci_lower"]))
        y_ci_u2 = y_pos(float(m["fa_ci_upper"]))
        x_mid2 = x_fa + (bar_width / 2.0)
        svg_parts.append(
            f'  <line x1="{x_mid2:.1f}" y1="{y_ci_u2:.1f}" x2="{x_mid2:.1f}" y2="{y_ci_l2:.1f}" stroke="#b91c1c" stroke-width="2"/>'
        )
        svg_parts.append(
            f'  <line x1="{x_mid2 - 5:.1f}" y1="{y_ci_u2:.1f}" x2="{x_mid2 + 5:.1f}" y2="{y_ci_u2:.1f}" stroke="#b91c1c" stroke-width="2"/>'
        )
        svg_parts.append(
            f'  <line x1="{x_mid2 - 5:.1f}" y1="{y_ci_l2:.1f}" x2="{x_mid2 + 5:.1f}" y2="{y_ci_l2:.1f}" stroke="#b91c1c" stroke-width="2"/>'
        )

        # X-axis label (model name & backend)
        short_name = m["model"]
        if "/" in short_name:
            short_name = short_name.split("/", 1)[1]
        svg_parts.append(
            f'  <text x="{x_center:.1f}" y="{chart_bottom + 22:.1f}" class="model-name">{short_name}</text>'
        )
        backend_label = f"({m['backend']})"
        svg_parts.append(
            f'  <text x="{x_center:.1f}" y="{chart_bottom + 38:.1f}" class="model-backend">{backend_label}</text>'
        )

    # Footer
    svg_parts.append(
        '  <text x="90" y="642" class="footer">Measured with `guard-rail-edge calibrate`. 95% Wilson score confidence interval shown.</text>'
    )
    svg_parts.append("</svg>\n")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(svg_parts), encoding="utf-8")


if __name__ == "__main__":
    data_file = Path("docs/data/judge_calibration.json")
    out_file = Path("assets/judge-calibration.svg")
    generate_judge_calibration_svg(data_file, out_file)
    print(f"Generated chart at {out_file}")

