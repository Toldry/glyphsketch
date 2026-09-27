"""Trivial baselines: nearest glyph render by raw pixels or by HOG features.

Both recognizers compare a rasterized drawing with every glyph render (all fonts) and
score each character by its best-matching render. They need no training, which makes them
a floor for the learned encoder, and show how far plain template matching gets.
"""

from collections.abc import Callable, Sequence

import numpy as np
from scipy.ndimage import gaussian_filter

from glyphsketch.glyphs import GlyphTable
from glyphsketch.strokes import Drawing, rasterize

PIXEL_IMAGE_SIZE = 32
PIXEL_BLUR_SIGMA = 1.0
HOG_IMAGE_SIZE = 64
HOG_ORIENTATIONS = 9
HOG_CELL = 8
QUERY_PEN_WIDTH_FRACTION = 0.07
QUERY_CHUNK = 256

FeatureFunction = Callable[[np.ndarray], np.ndarray]


def downsample_renders(renders: np.ndarray, size: int, chunk: int = 4096) -> np.ndarray:
    """Average-pool 128 px renders to ``size`` px (float32, 0..1)."""
    factor = renders.shape[1] // size
    pooled = np.empty((renders.shape[0], size, size), dtype=np.float32)
    for start in range(0, renders.shape[0], chunk):
        block = np.asarray(renders[start : start + chunk], dtype=np.float32) / 255.0
        pooled[start : start + chunk] = block.reshape(-1, size, factor, size, factor).mean(
            axis=(2, 4)
        )
    return pooled


def normalize_rows(features: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(features, axis=1, keepdims=True)
    normalized: np.ndarray = (features / np.maximum(norms, 1e-8)).astype(np.float32)
    return normalized


def pixel_features(images: np.ndarray) -> np.ndarray:
    """Blurred, mean-centered, L2-normalized pixels (images: float 0..1, shape (N, S, S))."""
    blurred: np.ndarray = gaussian_filter(images, sigma=(0, PIXEL_BLUR_SIGMA, PIXEL_BLUR_SIGMA))
    flat = blurred.reshape(len(images), -1)
    return normalize_rows(flat - flat.mean(axis=1, keepdims=True))


def hog_features(images: np.ndarray, chunk: int = 512) -> np.ndarray:
    """L2-normalized HOG descriptors of a batch (images: float 0..1, shape (N, S, S)).

    Dalal-Triggs HOG computed for the whole batch at once: central-difference gradients,
    unsigned orientations in ``HOG_ORIENTATIONS`` bins, ``HOG_CELL`` px cells, 2x2-cell
    blocks with L2-Hys normalization.
    """
    return normalize_rows(
        np.concatenate(
            [_hog_chunk(images[start : start + chunk]) for start in range(0, len(images), chunk)]
        )
    )


def _hog_chunk(images: np.ndarray) -> np.ndarray:
    count, size, _ = images.shape
    cells = size // HOG_CELL
    gradient_x = np.zeros_like(images)
    gradient_y = np.zeros_like(images)
    gradient_x[:, :, 1:-1] = images[:, :, 2:] - images[:, :, :-2]
    gradient_y[:, 1:-1, :] = images[:, 2:, :] - images[:, :-2, :]
    magnitude = np.hypot(gradient_x, gradient_y)
    orientation = np.rad2deg(np.arctan2(gradient_y, gradient_x)) % 180.0
    bins = np.minimum((orientation / (180.0 / HOG_ORIENTATIONS)).astype(np.int64), 8)
    histograms = np.zeros((count, cells, cells, HOG_ORIENTATIONS), dtype=np.float32)
    for orientation_bin in range(HOG_ORIENTATIONS):
        weighted = np.where(bins == orientation_bin, magnitude, 0.0)
        pooled = weighted.reshape(count, cells, HOG_CELL, cells, HOG_CELL).sum(axis=(2, 4))
        histograms[..., orientation_bin] = pooled
    blocks = np.stack(
        [
            histograms[:, dy : cells - 1 + dy, dx : cells - 1 + dx, :]
            for dy in range(2)
            for dx in range(2)
        ],
        axis=3,
    ).reshape(count, cells - 1, cells - 1, -1)
    epsilon = 1e-5
    blocks = blocks / np.sqrt((blocks**2).sum(axis=-1, keepdims=True) + epsilon**2)
    blocks = np.minimum(blocks, 0.2)
    blocks = blocks / np.sqrt((blocks**2).sum(axis=-1, keepdims=True) + epsilon**2)
    features: np.ndarray = blocks.reshape(count, -1)
    return features


def rasterize_queries(drawings: Sequence[Drawing], image_size: int) -> np.ndarray:
    pen_width = QUERY_PEN_WIDTH_FRACTION * image_size
    return (
        np.stack(
            [rasterize(drawing, image_size=image_size, pen_width=pen_width) for drawing in drawings]
        ).astype(np.float32)
        / 255.0
    )


class NearestGlyphRecognizer:
    """Rank characters by the cosine similarity of their best-matching render."""

    def __init__(
        self,
        index_features: np.ndarray,
        render_code_points: np.ndarray,
        feature_function: FeatureFunction,
        image_size: int,
    ) -> None:
        order = np.argsort(render_code_points, kind="stable")
        self.index_features = index_features[order]
        sorted_code_points = render_code_points[order]
        self.group_starts = np.flatnonzero(
            np.r_[True, sorted_code_points[1:] != sorted_code_points[:-1]]
        )
        self.code_points = sorted_code_points[self.group_starts]
        self.feature_function = feature_function
        self.image_size = image_size

    def character_scores(self, query_features: np.ndarray) -> np.ndarray:
        """(queries, characters) best similarity of each character's renders."""
        similarities = query_features @ self.index_features.T
        return np.maximum.reduceat(similarities, self.group_starts, axis=1)

    def rank(self, drawings: Sequence[Drawing], k: int) -> np.ndarray:
        results = []
        for start in range(0, len(drawings), QUERY_CHUNK):
            images = rasterize_queries(drawings[start : start + QUERY_CHUNK], self.image_size)
            scores = self.character_scores(self.feature_function(images))
            count = min(k, scores.shape[1])
            top = np.argpartition(-scores, count - 1, axis=1)[:, :count]
            top_scores = np.take_along_axis(scores, top, axis=1)
            ordered = np.take_along_axis(top, np.argsort(-top_scores, axis=1), axis=1)
            results.append(self.code_points[ordered])
        return np.concatenate(results)


def pixel_recognizer(renders: np.ndarray, table: GlyphTable) -> NearestGlyphRecognizer:
    index = pixel_features(downsample_renders(renders, PIXEL_IMAGE_SIZE))
    return NearestGlyphRecognizer(index, table.code_points, pixel_features, PIXEL_IMAGE_SIZE)


def hog_recognizer(renders: np.ndarray, table: GlyphTable) -> NearestGlyphRecognizer:
    index = hog_features(downsample_renders(renders, HOG_IMAGE_SIZE))
    return NearestGlyphRecognizer(index, table.code_points, hog_features, HOG_IMAGE_SIZE)
