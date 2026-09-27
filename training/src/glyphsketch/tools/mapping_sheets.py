"""Draw review sheets for the real-data label mappings.

Each row shows a dataset label, the font glyph of the code point it is mapped to (or an
empty tile if it has none) and a few drawings from the dataset, so a wrong mapping stands
out at a glance.

Usage::

    uv run python -m glyphsketch.tools.mapping_sheets detexify -o /tmp/sheets
    uv run python -m glyphsketch.tools.mapping_sheets omniglot -o /tmp/sheets
"""

import argparse
import sys
from collections import defaultdict
from collections.abc import Iterator, Sequence
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from glyphsketch.glyphs import GlyphTable, load_renders
from glyphsketch.paths import stage_dir
from glyphsketch.realdata import detexify, omniglot
from glyphsketch.strokes import rasterize

TILE = 48
DRAWINGS_PER_ROW = 6
ROWS_PER_SHEET = 40


def _tile_from_render(render: np.ndarray) -> np.ndarray:
    image = Image.fromarray(255 - np.asarray(render)).resize((TILE, TILE), Image.Resampling.BOX)
    return np.asarray(image)


def _label_tile(text: str, width: int) -> np.ndarray:
    image = Image.new("L", (width, TILE), 255)
    draw = ImageDraw.Draw(image)
    draw.text((3, 6), text[:34], fill=0)
    draw.text((3, 26), text[34:68], fill=0)
    return np.asarray(image)


def review_rows(
    rows: Sequence[tuple[str, int | None, list[list[np.ndarray]]]],
    renders: np.ndarray,
    table: GlyphTable,
) -> Iterator[Image.Image]:
    """Yield sheets of rows (label, mapped code point, drawings)."""
    first_row: dict[int, int] = {}
    for row_index, code_point in enumerate(table.code_points.tolist()):
        first_row.setdefault(code_point, row_index)
    for start in range(0, len(rows), ROWS_PER_SHEET):
        lines = []
        for label, code_point, drawings in rows[start : start + ROWS_PER_SHEET]:
            code_text = f"U+{code_point:04X}" if code_point is not None else "none"
            tiles = [_label_tile(f"{label} -> {code_text}", 220)]
            glyph = np.full((TILE, TILE), 200, dtype=np.uint8)
            if code_point is not None and code_point in first_row:
                glyph = _tile_from_render(renders[first_row[code_point]])
            tiles.append(glyph)
            for strokes in drawings[:DRAWINGS_PER_ROW]:
                tiles.append(255 - rasterize(strokes, image_size=TILE))
            tiles += [np.full((TILE, TILE), 255, np.uint8)] * (DRAWINGS_PER_ROW + 2 - len(tiles))
            line = np.concatenate(tiles, axis=1).copy()
            line[-1, :] = 128
            lines.append(line)
        yield Image.fromarray(np.concatenate(lines, axis=0))


def detexify_rows() -> list[tuple[str, int | None, list[list[np.ndarray]]]]:
    mapping = detexify.load_mapping()
    drawings: dict[str, list[list[np.ndarray]]] = defaultdict(list)
    for record in detexify.parse_dump(stage_dir("detexify") / detexify.DUMP_FILE):
        if len(drawings[record.key]) < DRAWINGS_PER_ROW and record.strokes:
            drawings[record.key].append(record.strokes)
    return [
        (entry.command, entry.code_point, drawings[key]) for key, entry in sorted(mapping.items())
    ]


def omniglot_rows() -> list[tuple[str, int | None, list[list[np.ndarray]]]]:
    mapping = omniglot.load_mapping()
    everything = {
        (entry.alphabet, entry.character_number): entry
        for entry in mapping.values()
        if entry.code_point is not None
    }
    drawings: dict[str, list[list[np.ndarray]]] = defaultdict(list)
    allowed = {entry.code_point for entry in everything.values() if entry.code_point}
    for sample in omniglot.omniglot_samples(stage_dir("omniglot"), mapping, allowed):
        if len(drawings[sample.label]) < DRAWINGS_PER_ROW:
            drawings[sample.label].append(list(sample.strokes))
    return [
        (
            f"{alphabet[:12]}/{number:02d}",
            entry.code_point,
            drawings[f"{alphabet}/character{number:02d}"],
        )
        for (alphabet, number), entry in sorted(everything.items())
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dataset", choices=["detexify", "omniglot"])
    parser.add_argument("-o", "--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    glyphs_dir = stage_dir("glyphs")
    table = GlyphTable.load(glyphs_dir)
    renders = load_renders(glyphs_dir)
    rows = detexify_rows() if args.dataset == "detexify" else omniglot_rows()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for number, sheet in enumerate(review_rows(rows, renders, table), start=1):
        path = args.output_dir / f"{args.dataset}_{number:02d}.png"
        sheet.save(path)
    print(f"Wrote {number} sheets for {len(rows)} labels to {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
