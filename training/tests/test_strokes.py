import numpy as np
import pytest

from glyphsketch.strokes import (
    CONTENT_FRACTION,
    fit_to_image,
    rasterize,
    segments_of,
    simplify_stroke,
)


def _ink_extent(image: np.ndarray, threshold: int = 128) -> tuple[int, int, int, int]:
    rows = np.flatnonzero(image.max(axis=1) >= threshold)
    columns = np.flatnonzero(image.max(axis=0) >= threshold)
    return int(rows[0]), int(rows[-1]), int(columns[0]), int(columns[-1])


def test_fit_centers_the_bounding_box_and_keeps_the_aspect_ratio() -> None:
    strokes = [np.array([[10.0, 20.0], [110.0, 20.0], [110.0, 70.0]])]
    (fitted,) = fit_to_image(strokes, 64)
    width = fitted[:, 0].max() - fitted[:, 0].min()
    height = fitted[:, 1].max() - fitted[:, 1].min()
    assert width == pytest.approx(CONTENT_FRACTION * 64)
    assert height == pytest.approx(CONTENT_FRACTION * 64 / 2)
    assert (fitted[:, 0].min() + fitted[:, 0].max()) / 2 == pytest.approx(32)
    assert (fitted[:, 1].min() + fitted[:, 1].max()) / 2 == pytest.approx(32)


def test_rasterized_square_spans_the_content_box() -> None:
    square = [np.array([[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]], dtype=np.float32)]
    image = rasterize(square, image_size=64, pen_width=2.0)
    assert image.shape == (64, 64) and image.dtype == np.uint8
    top, bottom, left, right = _ink_extent(image)
    expected = CONTENT_FRACTION * 64
    assert bottom - top + 1 == pytest.approx(expected + 2, abs=1)
    assert right - left + 1 == pytest.approx(expected + 2, abs=1)
    assert image[32, 32] == 0, "the inside of the square stays empty"


def test_a_tap_renders_as_a_centered_dot() -> None:
    image = rasterize([np.array([[5.0, 5.0]])], image_size=64, pen_width=4.0)
    top, bottom, left, right = _ink_extent(image)
    assert (top + bottom) / 2 == pytest.approx(31.5, abs=0.5)
    assert (left + right) / 2 == pytest.approx(31.5, abs=0.5)
    assert bottom - top <= 4


def test_line_width_follows_the_pen_width() -> None:
    horizontal = [np.array([[0.0, 50.0], [100.0, 50.0]])]
    thin = rasterize(horizontal, image_size=64, pen_width=2.0)
    thick = rasterize(horizontal, image_size=64, pen_width=6.0)
    assert (thick[:, 32] > 0).sum() > (thin[:, 32] > 0).sum()
    assert thin[32, 32] == 255


def test_simplification_keeps_end_points_and_drops_collinear_points() -> None:
    points = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0], [3.0, 0.0], [3.0, 3.0]])
    simplified = simplify_stroke(points, tolerance=0.1)
    assert simplified.tolist() == [[0.0, 0.0], [3.0, 0.0], [3.0, 3.0]]


def test_segments_include_single_points() -> None:
    segments = segments_of([np.array([[1.0, 2.0]]), np.array([[0.0, 0.0], [1.0, 1.0]])])
    assert segments.tolist() == [[1.0, 2.0, 1.0, 2.0], [0.0, 0.0, 1.0, 1.0]]


def test_empty_drawings_are_rejected() -> None:
    with pytest.raises(ValueError):
        rasterize([np.zeros((0, 2))])
