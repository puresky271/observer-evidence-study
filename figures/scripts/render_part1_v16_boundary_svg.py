"""Render an SVG of the Part I evidence and gate boundaries without dependencies."""
from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    source = root / "figures" / "source_data" / "part1_v16_gate_summary.json"
    output = root / "figures" / "exported" / "fig4_part1_evidence_boundary.svg"
    data = json.loads(source.read_text(encoding="utf-8"))
    rows = [
        ("sealed projection conditions", data["sealed_projection_conditions"], "#0072B2"),
        ("reference-sensitive nested arms", data["reference_sensitive_nested_arms"], "#D55E00"),
        ("distinct hidden perturbations", data["distinct_hidden_perturbations"], "#009E73"),
        ("informative hidden comparisons", data["informative_hidden_comparisons"], "#CC79A7"),
        ("validity projection conditions", data["validity_projection_conditions"], "#56B4E9"),
    ]
    width, height, left, max_width = 920, 440, 310, 500
    maximum = max(value for _label, value, _color in rows)
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<title>Part I evidence boundary</title>',
        '<desc>Nested observation counts are shown separately from distinct perturbations and informative comparisons.</desc>',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="40" y="38" font-family="sans-serif" font-size="22">Part I evidence boundary</text>',
    ]
    for index, (label, value, color) in enumerate(rows):
        y = 80 + index * 58
        bar = round(max_width * value / maximum)
        elements.extend([
            f'<text x="40" y="{y + 20}" font-family="sans-serif" font-size="15">{label}</text>',
            f'<rect x="{left}" y="{y + 5}" width="{bar}" height="26" fill="{color}"/>',
            f'<text x="{left + bar + 10}" y="{y + 24}" font-family="sans-serif" font-size="15">{value}</text>',
        ])
    elements.extend([
        '<text x="40" y="390" font-family="sans-serif" font-size="13">Family is the independent unit; nested arms are not independent samples.</text>',
        '<text x="40" y="412" font-family="sans-serif" font-size="13">Gate: PASS, 120 checks, 0 vacuous checks, 0 model calls, 0 harness executions.</text>',
        '</svg>',
    ])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(elements) + "\n", encoding="utf-8")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
