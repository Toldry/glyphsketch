"""Make the project logo and favicon from the "GS" drawing in docs/logo/gs-drawing.json.

The SVGs look like the demo's drawing pad in its dark theme (web/demo/style.css): light
round-capped strokes on the grey pad, with rounded corners. ``logo.svg`` uses the pad's
pen width; ``favicon.svg`` uses a thicker line, because at 16–32 px the pad's width would
be under a pixel.

Usage: ``uv run python -m glyphsketch.tools.logo``
"""

import json

import numpy as np

from glyphsketch.paths import REPO_ROOT
from glyphsketch.strokes import simplify_stroke

LOGO_DIR = REPO_ROOT / "docs" / "logo"
DRAWING_FILE = LOGO_DIR / "gs-drawing.json"
INK = "#ececf0"  # --ink, dark theme
PAD = "#222228"  # --panel, dark theme
PAD_PEN_WIDTH = 6.0  # the demo draws 6 CSS px lines
PAD_CORNER = 8.0 / 340  # 8 px radius on the 340 px pad
MARGIN = 0.14  # of the square's side, around the drawing
SIMPLIFY_TOLERANCE = 0.4  # CSS px


def svg(strokes: list[np.ndarray], pen_width: float, size: int = 256) -> str:
    points = np.concatenate(strokes)
    low, high = points.min(axis=0), points.max(axis=0)
    extent = float(max(high - low))
    side = extent / (1 - 2 * MARGIN)
    centre = (low + high) / 2
    origin = centre - side / 2
    scale = size / side
    paths = []
    for stroke in strokes:
        simplified = simplify_stroke(stroke, SIMPLIFY_TOLERANCE)
        coordinates = " ".join(
            f"{(x - origin[0]) * scale:.1f},{(y - origin[1]) * scale:.1f}" for x, y in simplified
        )
        paths.append(f'  <polyline points="{coordinates}"/>')
    corner = PAD_CORNER * size * 2
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
            f'width="{size}" height="{size}">',
            "  <title>glyphsketch</title>",
            f'  <rect width="{size}" height="{size}" rx="{corner:.1f}" fill="{PAD}"/>',
            f'  <g fill="none" stroke="{INK}" stroke-width="{pen_width * scale:.1f}" '
            'stroke-linecap="round" stroke-linejoin="round">',
            *["  " + path for path in paths],
            "  </g>",
            "</svg>",
            "",
        ]
    )


def main() -> None:
    raw = json.loads(DRAWING_FILE.read_text(encoding="utf-8"))
    strokes = [np.array(stroke, dtype=np.float64) for stroke in raw["strokes"]]
    outputs = {
        LOGO_DIR / "logo.svg": svg(strokes, PAD_PEN_WIDTH),
        LOGO_DIR / "favicon.svg": svg(strokes, PAD_PEN_WIDTH * 2.5),
    }
    for path, content in outputs.items():
        path.write_text(content, encoding="utf-8")
        print(f"{path.relative_to(REPO_ROOT)}: {len(content)} bytes")


if __name__ == "__main__":
    main()
