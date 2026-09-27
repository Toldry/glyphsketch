"""Draw a gallery comparing synthetic drawings with real ones.

Each row: the character's first glyph render, then synthetic samples, then (after a gap)
real drawings of the same character from the test data, if any.

Usage::

    uv run python -m glyphsketch.tools.synthetic_gallery --chars "aAgж∑→" -o gallery.png
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from PIL import Image

from glyphsketch.fonts import load_font_manifest
from glyphsketch.glyphs import GlyphTable, load_renders
from glyphsketch.paths import stage_dir
from glyphsketch.realdata.build import SAMPLES_FILE
from glyphsketch.realdata.samples import SampleSet
from glyphsketch.strokes import rasterize
from glyphsketch.synth.generator import GLYPH_STROKES_FILE, GlyphStrokeTable, SyntheticGenerator

TILE = 64


def _frame(tile: np.ndarray) -> np.ndarray:
    framed = (255 - tile).copy()
    framed[0, :] = 170
    framed[:, 0] = 170
    return framed


def gallery(
    generator: SyntheticGenerator,
    renders: np.ndarray,
    table: GlyphTable,
    real: SampleSet | None,
    code_points: Sequence[int],
    synthetic_per_row: int = 10,
    real_per_row: int = 5,
) -> Image.Image:
    rows = []
    blank = np.full((TILE, TILE), 255, dtype=np.uint8)
    for code_point in code_points:
        render_rows = table.rows_for(code_point)
        glyph = np.asarray(
            Image.fromarray(np.asarray(renders[render_rows[0]])).resize(
                (TILE, TILE), Image.Resampling.BOX
            )
        )
        tiles = [_frame(glyph), blank]
        tiles += [_frame(generator.image(code_point, index)) for index in range(synthetic_per_row)]
        tiles.append(blank)
        if real is not None:
            for index in np.flatnonzero(real.code_points == code_point)[:real_per_row]:
                tiles.append(_frame(rasterize(real.strokes(int(index)), image_size=TILE)))
        tiles += [blank] * (synthetic_per_row + real_per_row + 3 - len(tiles))
        rows.append(np.concatenate(tiles, axis=1))
    return Image.fromarray(np.concatenate(rows, axis=0))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--chars", required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args(argv)
    glyphs_dir = stage_dir("glyphs")
    table = GlyphTable.load(glyphs_dir)
    strokes = GlyphStrokeTable.load(stage_dir("glyphstrokes") / GLYPH_STROKES_FILE)
    styles = {spec.id: spec.style for spec in load_font_manifest().fonts}
    generator = SyntheticGenerator(strokes, table, styles, seed=args.seed)
    real_path = stage_dir("realdata") / SAMPLES_FILE
    real = SampleSet.load(real_path) if real_path.exists() else None
    code_points = [ord(char) for char in args.chars if ord(char) in generator.rows]
    image = gallery(generator, load_renders(glyphs_dir), table, real, code_points)
    image.save(args.output)
    print(f"Wrote {args.output} ({len(code_points)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
