"""Build the de-identified Part I evidence-plane overview in PDF and SVG."""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import landscape, A4
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent
OUT = HERE / "figures"
PDF = OUT / "part1_evidence_plane_overview.pdf"
SVG = OUT / "part1_evidence_plane_overview.svg"

W, H = landscape(A4)

BOXES = [
    ("source registry", 36, 330, 132, 48, "#E8F1F8"),
    ("observer evidence", 204, 390, 140, 48, "#E8F1F8"),
    ("refresh trace", 204, 315, 140, 48, "#E8F1F8"),
    ("projection / context", 390, 350, 156, 52, "#D9EEE6"),
    ("evaluator-only Oracle", 204, 185, 140, 48, "#F7E5D5"),
    ("gate audit", 590, 350, 130, 52, "#F5E6B8"),
    ("v16 delivery boundary", 590, 185, 160, 52, "#E5E5E5"),
]

EDGES = [
    ((168, 354), (204, 414)),
    ((168, 354), (204, 339)),
    ((344, 414), (390, 376)),
    ((344, 339), (390, 376)),
    ((546, 376), (590, 376)),
    ((344, 209), (655, 350)),
    ((655, 350), (655, 237)),
]


def wrap_lines(label: str) -> list[str]:
    return label.split(" / ") if " / " in label else [label]


def draw_pdf() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(PDF), pagesize=landscape(A4))
    c.setTitle("Part I evidence-plane overview")
    c.setFillColor(HexColor("#FFFFFF"))
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setFillColor(HexColor("#1F2933"))
    c.setFont("Helvetica-Bold", 15)
    c.drawString(36, 548, "Part I: evidence planes and audit boundary")
    c.setFont("Helvetica", 8.5)
    c.setFillColor(HexColor("#4B5563"))
    c.drawString(36, 532, "The evaluator-only Oracle is retained for checking but excluded from observer-visible context.")
    c.setStrokeColor(HexColor("#4B5563"))
    c.setLineWidth(1.2)
    for (x1, y1), (x2, y2) in EDGES:
        c.line(x1, y1, x2, y2)
        c.line(x2, y2, x2 - 5, y2 + 3)
        c.line(x2, y2, x2 - 5, y2 - 3)
    for label, x, y, width, height, color in BOXES:
        c.setFillColor(HexColor(color))
        c.setStrokeColor(HexColor("#334E68"))
        c.roundRect(x, y, width, height, 5, stroke=1, fill=1)
        c.setFillColor(HexColor("#1F2933"))
        c.setFont("Helvetica-Bold", 9)
        lines = wrap_lines(label)
        for i, line in enumerate(lines):
            c.drawCentredString(x + width / 2, y + height / 2 + 4 - i * 12, line)
    c.setFillColor(HexColor("#1F2933"))
    c.setFont("Helvetica", 8)
    c.drawString(36, 105, "v16 evidence: 288 sealed projection conditions; 216 nested arms; 9 distinct hidden perturbations; 120 gate checks.")
    c.drawString(36, 91, "Release: only derived, opaque, aggregate artifacts cross the public boundary; source and hidden labels remain local.")
    c.showPage()
    c.save()


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def draw_svg() -> None:
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="842" height="595" viewBox="0 0 842 595">',
        '<title>Part I evidence planes and audit boundary</title>',
        '<desc>De-identified schematic of source registry, observer evidence, evaluator-only Oracle, projection, gate audit and delivery boundary.</desc>',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="36" y="48" font-family="sans-serif" font-size="20" font-weight="700" fill="#1F2933">Part I: evidence planes and audit boundary</text>',
        '<text x="36" y="68" font-family="sans-serif" font-size="11" fill="#4B5563">The evaluator-only Oracle is retained for checking but excluded from observer-visible context.</text>',
    ]
    for (x1, y1), (x2, y2) in EDGES:
        sy1, sy2 = 595 - y1, 595 - y2
        elements.append(f'<line x1="{x1}" y1="{sy1}" x2="{x2}" y2="{sy2}" stroke="#4B5563" stroke-width="2"/>')
        elements.append(f'<polygon points="{x2},{sy2} {x2-7},{sy2-4} {x2-7},{sy2+4}" fill="#4B5563"/>')
    for label, x, y, width, height, color in BOXES:
        sy = 595 - y - height
        elements.append(f'<rect x="{x}" y="{sy}" width="{width}" height="{height}" rx="6" fill="{color}" stroke="#334E68" stroke-width="1.5"/>')
        lines = wrap_lines(label)
        for i, line in enumerate(lines):
            ty = sy + height / 2 + 4 - i * 12
            elements.append(f'<text x="{x + width/2}" y="{ty}" text-anchor="middle" font-family="sans-serif" font-size="11" font-weight="700" fill="#1F2933">{esc(line)}</text>')
    elements.extend([
        '<text x="36" y="490" font-family="sans-serif" font-size="10" fill="#1F2933">v16 evidence: 288 sealed projection conditions; 216 nested arms; 9 distinct hidden perturbations; 120 gate checks.</text>',
        '<text x="36" y="507" font-family="sans-serif" font-size="10" fill="#1F2933">Release: only derived, opaque, aggregate artifacts cross the public boundary; source and hidden labels remain local.</text>',
        '</svg>',
    ])
    SVG.write_text("\n".join(elements) + "\n", encoding="utf-8")


if __name__ == "__main__":
    draw_pdf()
    draw_svg()
    print(PDF)
    print(SVG)
