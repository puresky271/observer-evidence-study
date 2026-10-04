"""Render a dependency-free SVG summary of the frozen no-model layers."""
from __future__ import annotations

import csv
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    source = root / "figures" / "source_data" / "part1_baseline_layers.csv"
    output = root / "figures" / "exported" / "fig3_part1_coverage.svg"
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(source.open(encoding="utf-8")))
    width, height = 900, 460
    max_value = max(int(row["conditions"]) for row in rows)
    bars = []
    for index, row in enumerate(rows):
        y = 80 + index * 80
        value = int(row["conditions"])
        bar_width = int(620 * value / max_value)
        bars.append(f'<text x="40" y="{y + 24}" font-size="16">{row["layer"]}</text>')
        bars.append(f'<rect x="240" y="{y + 8}" width="{bar_width}" height="28" fill="#0072B2"/>')
        bars.append(f'<text x="{250 + bar_width}" y="{y + 28}" font-size="16">{value} conditions / {row["families"]} families</text>')
    svg = "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<title>Frozen Part I no-model coverage layers</title>',
        '<desc>Condition counts and family counts for the development, sealed, validity, and V1.5 external-validity layers.</desc>',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="40" y="38" font-size="22" font-family="sans-serif">Frozen Part I coverage layers</text>',
        *bars,
        '<text x="40" y="420" font-size="14" font-family="sans-serif">Conditions are nested observations; family is the independent unit.</text>',
        '</svg>',
    ])
    output.write_text(svg + "\n", encoding="utf-8")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
