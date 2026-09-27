"""Synthetic drawings: glyph strokes, distorted by ``augment``, rasterized like real input.

The ``glyphstrokes`` stage extracts the strokes of every glyph render once
(``glyph_strokes.npz``, rows aligned with the glyph table). ``SyntheticGenerator`` then
turns (code point, sample index) into a drawing deterministically: the seed, code point
and sample index seed a NumPy generator, which picks one of the character's renders (fonts
weighted by style) and every distortion.
"""

import multiprocessing
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from glyphsketch.glyphs import GlyphTable, load_renders
from glyphsketch.strokes import rasterize
from glyphsketch.synth.augment import AugmentationConfig, augment_strokes, pen_width_for
from glyphsketch.synth.skeleton import glyph_strokes

GLYPH_STROKES_FILE = "glyph_strokes.npz"
# How often each font style is picked relative to the others. Handwriting-style fonts are
# closest to drawn input; serif fonts leave serif ticks in their skeletons.
STYLE_WEIGHTS = {
    "handwriting": 3.0,
    "sans": 2.0,
    "mono": 1.0,
    "serif": 1.0,
    "math": 1.0,
    "symbols": 1.5,
}


@dataclass(frozen=True)
class GlyphStrokeTable:
    """Strokes of every glyph render, in render pixel coordinates."""

    points: np.ndarray
    stroke_offsets: np.ndarray
    render_offsets: np.ndarray

    def __len__(self) -> int:
        return len(self.render_offsets) - 1

    def strokes(self, row: int) -> list[np.ndarray]:
        first, last = self.render_offsets[row], self.render_offsets[row + 1]
        return [
            self.points[self.stroke_offsets[s] : self.stroke_offsets[s + 1]].astype(np.float64)
            for s in range(first, last)
        ]

    def stroke_count(self, row: int) -> int:
        return int(self.render_offsets[row + 1] - self.render_offsets[row])

    @classmethod
    def from_stroke_lists(cls, stroke_lists: Sequence[Sequence[np.ndarray]]) -> "GlyphStrokeTable":
        points: list[np.ndarray] = []
        stroke_offsets = [0]
        render_offsets = [0]
        for strokes in stroke_lists:
            for stroke in strokes:
                points.append(np.asarray(stroke, dtype=np.float32).reshape(-1, 2))
                stroke_offsets.append(stroke_offsets[-1] + len(points[-1]))
            render_offsets.append(len(stroke_offsets) - 1)
        return cls(
            points=np.concatenate(points) if points else np.zeros((0, 2), np.float32),
            stroke_offsets=np.array(stroke_offsets, dtype=np.int64),
            render_offsets=np.array(render_offsets, dtype=np.int64),
        )

    def save(self, path: Path) -> None:
        np.savez_compressed(
            path,
            points=self.points,
            stroke_offsets=self.stroke_offsets,
            render_offsets=self.render_offsets,
        )

    @classmethod
    def load(cls, path: Path) -> "GlyphStrokeTable":
        with np.load(path) as data:
            return cls(data["points"], data["stroke_offsets"], data["render_offsets"])


def _extract_rows(arguments: tuple[str, int, int]) -> list[list[np.ndarray]]:
    glyphs_dir, start, stop = arguments
    renders = load_renders(Path(glyphs_dir))
    boxes = GlyphTable.load(Path(glyphs_dir)).ink_boxes_em
    extents = np.maximum(boxes[:, 2] - boxes[:, 0], boxes[:, 3] - boxes[:, 1])
    return [
        glyph_strokes(np.asarray(renders[row]), float(extents[row])) for row in range(start, stop)
    ]


def extract_all_strokes(glyphs_dir: Path, workers: int | None = None) -> GlyphStrokeTable:
    count = load_renders(glyphs_dir).shape[0]
    chunk = 500
    tasks = [
        (str(glyphs_dir), start, min(start + chunk, count)) for start in range(0, count, chunk)
    ]
    workers = workers or max(1, multiprocessing.cpu_count() - 2)
    with multiprocessing.get_context("spawn").Pool(workers) as pool:
        chunks = pool.map(_extract_rows, tasks, chunksize=1)
    return GlyphStrokeTable.from_stroke_lists([strokes for part in chunks for strokes in part])


@dataclass(frozen=True)
class SyntheticDrawing:
    strokes: list[np.ndarray]
    pen_width: float
    render_row: int


class SyntheticGenerator:
    def __init__(
        self,
        stroke_table: GlyphStrokeTable,
        glyph_table: GlyphTable,
        font_styles: dict[str, str],
        config: AugmentationConfig | None = None,
        image_size: int = 64,
        seed: int = 0,
    ) -> None:
        self.stroke_table = stroke_table
        self.config = config or AugmentationConfig()
        self.image_size = image_size
        self.seed = seed
        rows_by_code_point: dict[int, list[int]] = {}
        for row, code_point in enumerate(glyph_table.code_points.tolist()):
            if stroke_table.stroke_count(row) > 0:
                rows_by_code_point.setdefault(code_point, []).append(row)
        self.rows = {cp: np.array(rows) for cp, rows in rows_by_code_point.items()}
        self.weights = {}
        for code_point, rows in self.rows.items():
            styles = [
                font_styles[glyph_table.font_ids[glyph_table.font_indices[row]]] for row in rows
            ]
            weights = np.array([STYLE_WEIGHTS[style] for style in styles])
            self.weights[code_point] = weights / weights.sum()

    @property
    def code_points(self) -> list[int]:
        return sorted(self.rows)

    def rng_for(self, code_point: int, sample_index: int) -> np.random.Generator:
        return np.random.default_rng([self.seed, code_point, sample_index])

    def drawing(self, code_point: int, sample_index: int) -> SyntheticDrawing:
        rng = self.rng_for(code_point, sample_index)
        rows = self.rows[code_point]
        row = int(rng.choice(rows, p=self.weights[code_point]))
        strokes = augment_strokes(self.stroke_table.strokes(row), self.config, rng)
        pen_width = pen_width_for(self.image_size, self.config, rng)
        return SyntheticDrawing(strokes=strokes, pen_width=pen_width, render_row=row)

    def image(self, code_point: int, sample_index: int) -> np.ndarray:
        drawing = self.drawing(code_point, sample_index)
        return rasterize(drawing.strokes, image_size=self.image_size, pen_width=drawing.pen_width)

    def images(self, requests: Sequence[tuple[int, int]]) -> np.ndarray:
        """Rasterized drawings for (code point, sample index) pairs, in order."""
        output = np.empty((len(requests), self.image_size, self.image_size), dtype=np.uint8)
        for position, (code_point, sample_index) in enumerate(requests):
            output[position] = self.image(code_point, sample_index)
        return output


_worker_generator: SyntheticGenerator | None = None


def _initialize_worker(generator: SyntheticGenerator) -> None:
    global _worker_generator
    _worker_generator = generator


def _generate_chunk(requests: list[tuple[int, int]]) -> np.ndarray:
    assert _worker_generator is not None
    return _worker_generator.images(requests)


def generate_images(
    generator: SyntheticGenerator,
    requests: Sequence[tuple[int, int]],
    workers: int | None = None,
    chunk: int = 256,
) -> np.ndarray:
    """``generator.images`` spread over worker processes; same output as a single process."""
    workers = workers or max(1, multiprocessing.cpu_count() - 2)
    if workers == 1 or len(requests) <= chunk:
        return generator.images(requests)
    parts = [list(requests[start : start + chunk]) for start in range(0, len(requests), chunk)]
    with multiprocessing.get_context("spawn").Pool(
        workers, initializer=_initialize_worker, initargs=(generator,)
    ) as pool:
        return np.concatenate(pool.map(_generate_chunk, parts, chunksize=1))
