import numpy as np
import pytest

from glyphsketch.baselines import (
    NearestGlyphRecognizer,
    downsample_renders,
    hog_features,
    normalize_rows,
    pixel_features,
)


def _bar_image(size: int, horizontal: bool) -> np.ndarray:
    image = np.zeros((size, size), dtype=np.float32)
    middle = slice(size // 2 - 2, size // 2 + 2)
    if horizontal:
        image[middle, 4:-4] = 1.0
    else:
        image[4:-4, middle] = 1.0
    return image


def test_downsampling_averages_blocks() -> None:
    renders = np.zeros((1, 128, 128), dtype=np.uint8)
    renders[0, :4, :4] = 255
    pooled = downsample_renders(renders, 32)
    assert pooled.shape == (1, 32, 32)
    assert pooled[0, 0, 0] == pytest.approx(1.0)
    assert pooled[0, 1, 1] == 0.0


def test_features_are_unit_vectors() -> None:
    images = np.stack([_bar_image(64, True), _bar_image(64, False)])
    for features in (hog_features(images), pixel_features(images)):
        assert np.allclose(np.linalg.norm(features, axis=1), 1.0, atol=1e-5)


def test_hog_tells_horizontal_from_vertical_strokes() -> None:
    horizontal = hog_features(np.stack([_bar_image(64, True), _bar_image(64, True)]))
    vertical = hog_features(np.stack([_bar_image(64, False)]))
    assert float(horizontal[0] @ horizontal[1]) == pytest.approx(1.0)
    assert float(horizontal[0] @ vertical[0]) < 0.5


def test_recognizer_scores_characters_by_their_best_render() -> None:
    index = normalize_rows(np.array([[1.0, 0.0], [0.0, 1.0], [0.6, 0.8], [0.8, 0.6]]))
    code_points = np.array([66, 65, 67, 65])
    recognizer = NearestGlyphRecognizer(index, code_points, lambda batch: batch, image_size=8)
    query = normalize_rows(np.array([[0.9, 0.1]]))
    scores = recognizer.character_scores(query)
    assert recognizer.code_points.tolist() == [65, 66, 67]
    assert scores.shape == (1, 3)
    assert scores[0, 0] == pytest.approx(float(index[3] @ query[0]))


def test_recognizer_ranks_distinct_characters() -> None:
    size = 32
    images = np.stack([_bar_image(size, True), _bar_image(size, False)])
    index = pixel_features(images)
    recognizer = NearestGlyphRecognizer(index, np.array([0x2D, 0x7C]), pixel_features, size)
    drawings = [
        [np.array([[0.0, 5.0], [10.0, 5.0]])],
        [np.array([[5.0, 0.0], [5.0, 10.0]])],
    ]
    ranking = recognizer.rank(drawings, k=2)
    assert ranking.tolist() == [[0x2D, 0x7C], [0x7C, 0x2D]]
