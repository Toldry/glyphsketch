"""Draw a contact sheet of glyph renders for visual inspection.

One row per character; the row starts with a label tile (the code point) and then shows
the character's renders from each font, in manifest order.

Usage::

    uv run python -m glyphsketch.tools.contact_sheet --block "Hebrew" -o hebrew.png
    uv run python -m glyphsketch.tools.contact_sheet --chars "aɑα" -o a.png
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from glyphsketch.charset import CHARSET_FILE_NAME, load_charset
from glyphsketch.glyphs import GlyphTable, load_renders
from glyphsketch.paths import stage_dir


def contact_sheet(
    renders: np.ndarray,
    table: GlyphTable,
    code_points: Sequence[int],
    *,
    tile_size: int = 48,
    max_fonts: int = 24,
) -> Image.Image:
    rows = []
    for code_point in code_points:
        label = Image.new("L", (tile_size * 2, tile_size), 255)
        ImageDraw.Draw(label).text((2, tile_size // 3), f"U+{code_point:04X}", fill=0)
        tiles = [np.asarray(label)]
        for row in table.rows_for(code_point)[:max_fonts]:
            glyph = Image.fromarray(255 - np.asarray(renders[row]))
            tile = np.asarray(glyph.resize((tile_size, tile_size), Image.Resampling.BOX)).copy()
            tile[0, :] = 160
            tile[:, 0] = 160
            tiles.append(tile)
        width = tile_size * (max_fonts + 2)
        row_image = np.full((tile_size, width), 255, dtype=np.uint8)
        joined = np.concatenate(tiles, axis=1)
        row_image[:, : joined.shape[1]] = joined
        rows.append(row_image)
    if not rows:
        raise ValueError("No characters to draw")
    return Image.fromarray(np.concatenate(rows, axis=0))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--block", help="Unicode block name, e.g. 'Hebrew'")
    selection.add_argument("--chars", help="the characters to show")
    parser.add_argument("--limit", type=int, default=64, help="maximum number of rows")
    parser.add_argument("--max-fonts", type=int, default=24)
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args(argv)

    glyphs_dir = stage_dir("glyphs")
    table = GlyphTable.load(glyphs_dir)
    if args.block:
        records = load_charset(stage_dir("charset") / CHARSET_FILE_NAME)
        code_points = [record.code_point for record in records if record.block == args.block]
    else:
        code_points = [ord(char) for char in args.chars]
    covered = set(table.code_points.tolist())
    code_points = [code_point for code_point in code_points if code_point in covered]
    sheet = contact_sheet(
        load_renders(glyphs_dir), table, code_points[: args.limit], max_fonts=args.max_fonts
    )
    sheet.save(args.output)
    print(f"Wrote {args.output} ({len(code_points[: args.limit])} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
