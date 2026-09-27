"""The glyph index and the embedding-based recognizer.

Two ways to build the index (PLAN.md, section 1, change 2):

* option (a), ``glyph``: embed every glyph render (one per font) of every character. A
  character can be represented by all of its render embeddings (a query scores the best
  one: ``per_font``) or by their normalized mean (one vector per character: ``mean``).
* option (b), ``synthetic``: embed K synthetic drawings of each character, generated with
  a seed that training did not use, and average them into one prototype.

Both need nothing but fonts, so adding a character never needs handwriting data.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import torch

from glyphsketch.model.encoder import GlyphEncoder
from glyphsketch.model.train import embed_uint8_images
from glyphsketch.strokes import DEFAULT_PEN_WIDTH_FRACTION, Drawing, rasterize
from glyphsketch.synth.generator import SyntheticGenerator, generate_images

INDEX_SEED = 1_000_003


@dataclass(frozen=True)
class GlyphIndex:
    """Index vectors, sorted by code point; rows ``starts[k]:starts[k + 1]`` belong to
    ``code_points[k]``."""

    vectors: np.ndarray
    code_points: np.ndarray
    starts: np.ndarray

    @classmethod
    def from_rows(cls, vectors: np.ndarray, row_code_points: np.ndarray) -> "GlyphIndex":
        order = np.argsort(row_code_points, kind="stable")
        sorted_code_points = row_code_points[order]
        starts = np.flatnonzero(np.r_[True, sorted_code_points[1:] != sorted_code_points[:-1]])
        return cls(vectors[order], sorted_code_points[starts], starts)

    def averaged(self) -> "GlyphIndex":
        """One normalized mean vector per character."""
        sums = np.add.reduceat(self.vectors, self.starts, axis=0)
        means = sums / np.maximum(np.linalg.norm(sums, axis=1, keepdims=True), 1e-8)
        return GlyphIndex(
            means.astype(np.float32), self.code_points, np.arange(len(self.code_points))
        )

    def scores(self, queries: np.ndarray) -> np.ndarray:
        """(queries, characters): best dot product over each character's vectors."""
        similarities = queries @ self.vectors.T
        if len(self.starts) == len(self.vectors):
            return similarities
        return np.maximum.reduceat(similarities, self.starts, axis=1)

    def top_k(self, queries: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
        scores = self.scores(queries)
        count = min(k, scores.shape[1])
        top = np.argpartition(-scores, count - 1, axis=1)[:, :count]
        top_scores = np.take_along_axis(scores, top, axis=1)
        order = np.argsort(-top_scores, axis=1)
        top = np.take_along_axis(top, order, axis=1)
        return self.code_points[top], np.take_along_axis(top_scores, order, axis=1)


def glyph_index(
    model: GlyphEncoder,
    glyph_images: np.ndarray,
    glyph_code_points: np.ndarray,
    device: torch.device,
) -> GlyphIndex:
    """Option (a): one vector per glyph render."""
    return GlyphIndex.from_rows(embed_uint8_images(model, glyph_images, device), glyph_code_points)


def synthetic_index(
    model: GlyphEncoder,
    generator: SyntheticGenerator,
    code_points: Sequence[int],
    samples_per_character: int,
    device: torch.device,
) -> GlyphIndex:
    """Option (b): the mean embedding of synthetic drawings of each character."""
    requests = [
        (code_point, INDEX_SEED + sample)
        for code_point in code_points
        for sample in range(samples_per_character)
    ]
    images = generate_images(generator, requests)
    embeddings = embed_uint8_images(model, images, device)
    rows = np.array([code_point for code_point, _ in requests], dtype=np.int64)
    return GlyphIndex.from_rows(embeddings, rows).averaged()


def rasterize_for_encoder(drawings: Sequence[Drawing], image_size: int = 64) -> np.ndarray:
    pen_width = DEFAULT_PEN_WIDTH_FRACTION * image_size
    return np.stack(
        [rasterize(drawing, image_size=image_size, pen_width=pen_width) for drawing in drawings]
    )


class EmbeddingRecognizer:
    """Rank characters by cosine similarity between the drawing and the index."""

    def __init__(self, model: GlyphEncoder, index: GlyphIndex, device: torch.device) -> None:
        self.model = model
        self.index = index
        self.device = device

    def rank_images(self, images: np.ndarray, k: int) -> np.ndarray:
        embeddings = embed_uint8_images(self.model, images, self.device)
        predictions = []
        for start in range(0, len(embeddings), 1024):
            predictions.append(self.index.top_k(embeddings[start : start + 1024], k)[0])
        return np.concatenate(predictions)

    def rank(self, drawings: Sequence[Drawing], k: int) -> np.ndarray:
        return self.rank_images(rasterize_for_encoder(drawings), k)
