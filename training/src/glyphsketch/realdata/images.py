"""Rasterize many real drawings at once, in worker processes."""

from collections.abc import Sequence

import numpy as np

from glyphsketch.parallel import default_workers, single_threaded_pool
from glyphsketch.realdata.samples import SampleSet
from glyphsketch.strokes import rasterize

_worker_samples: SampleSet | None = None


def _initialize(samples: SampleSet) -> None:
    global _worker_samples
    _worker_samples = samples


def _rasterize_rows(task: tuple[list[int], list[float], int]) -> np.ndarray:
    rows, pen_widths, image_size = task
    assert _worker_samples is not None
    return np.stack(
        [
            rasterize(_worker_samples.strokes(row), image_size=image_size, pen_width=pen)
            for row, pen in zip(rows, pen_widths, strict=True)
        ]
    )


def rasterize_samples(
    samples: SampleSet,
    image_size: int,
    pen_widths: Sequence[float] | np.ndarray,
    workers: int | None = None,
    chunk: int = 512,
) -> np.ndarray:
    """uint8 (len(samples), S, S) images; ``pen_widths`` in pixels, one per sample."""
    pens = [float(width) for width in pen_widths]
    if len(pens) != len(samples):
        raise ValueError("Need one pen width per sample")
    rows = list(range(len(samples)))
    tasks = [
        (rows[start : start + chunk], pens[start : start + chunk], image_size)
        for start in range(0, len(rows), chunk)
    ]
    if not tasks:
        return np.zeros((0, image_size, image_size), dtype=np.uint8)
    workers = workers or default_workers(len(tasks))
    if workers == 1 or len(tasks) == 1:
        _initialize(samples)
        return np.concatenate([_rasterize_rows(task) for task in tasks])
    with single_threaded_pool(workers, _initialize, (samples,)) as pool:
        return np.concatenate(pool.map(_rasterize_rows, tasks, chunksize=1))
