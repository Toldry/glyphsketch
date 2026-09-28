import numpy as np

from glyphsketch.detypify import CANVAS_SIZE, MARGIN, detypify_image


def test_the_drawing_is_fitted_into_the_canvas_minus_the_margin() -> None:
    image = detypify_image([np.array([[0.0, 0.0], [10.0, 0.0]])])
    assert image.shape == (CANVAS_SIZE, CANVAS_SIZE) and image.dtype == np.float32
    columns = np.flatnonzero(image.max(axis=0) > 0.5)
    rows = np.flatnonzero(image.max(axis=1) > 0.5)
    half_span = (CANVAS_SIZE - MARGIN) / 2
    assert abs(columns[0] - (CANVAS_SIZE / 2 - half_span)) <= 5
    assert abs(columns[-1] - (CANVAS_SIZE / 2 + half_span)) <= 5
    assert 6 <= len(rows) <= 10  # an 8 px line


def test_single_point_strokes_draw_nothing_as_on_a_canvas() -> None:
    image = detypify_image([np.array([[0.0, 0.0], [0.0, 10.0]]), np.array([[5.0, 5.0]])])
    assert image[:, CANVAS_SIZE // 2 + 40 :].max() == 0
    assert not detypify_image([np.array([[3.0, 3.0]])]).any()
