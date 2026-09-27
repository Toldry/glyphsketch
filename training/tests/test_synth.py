import numpy as np
import pytest

from conftest import real_stage_dir_or_skip
from glyphsketch.glyphs import GlyphTable
from glyphsketch.synth.augment import (
    AugmentationConfig,
    augment_strokes,
    change_endpoints,
    normalize_strokes,
    pen_width_for,
    resample,
    smooth_corners,
)
from glyphsketch.synth.generator import GLYPH_STROKES_FILE, GlyphStrokeTable, SyntheticGenerator
from glyphsketch.synth.skeleton import glyph_strokes


def _canvas() -> np.ndarray:
    return np.zeros((128, 128), dtype=np.uint8)


def _stroke_extent(stroke: np.ndarray) -> tuple[float, float]:
    return float(np.ptp(stroke[:, 0])), float(np.ptp(stroke[:, 1]))


def test_a_thick_bar_becomes_one_straight_stroke() -> None:
    render = _canvas()
    render[58:70, 10:118] = 255
    strokes = glyph_strokes(render)
    assert len(strokes) == 1
    width, height = _stroke_extent(strokes[0])
    assert width > 90 and height < 4


def test_a_ring_becomes_one_closed_loop() -> None:
    yy, xx = np.mgrid[:128, :128]
    radius = np.hypot(yy - 64, xx - 64)
    render = _canvas()
    render[(radius > 40) & (radius < 52)] = 255
    strokes = glyph_strokes(render)
    assert len(strokes) == 1
    loop = strokes[0]
    assert np.hypot(*(loop[0] - loop[-1])) < 3
    distances = np.hypot(loop[:, 0] - 64, loop[:, 1] - 64)
    assert np.all(np.abs(distances - 46) < 4)


def test_a_t_becomes_a_bar_and_a_stem() -> None:
    render = _canvas()
    render[10:22, 10:118] = 255
    render[10:118, 58:70] = 255
    strokes = glyph_strokes(render)
    assert len(strokes) == 2
    extents = sorted(_stroke_extent(stroke) for stroke in strokes)
    assert extents[0][0] < 6 and extents[0][1] > 80
    assert extents[1][0] > 90 and extents[1][1] < 6


def test_a_plus_becomes_two_crossing_strokes() -> None:
    render = _canvas()
    render[58:70, 10:118] = 255
    render[10:118, 58:70] = 255
    assert len(glyph_strokes(render)) == 2


def test_short_spurs_are_pruned() -> None:
    render = _canvas()
    render[58:70, 10:118] = 255
    render[53:58, 60:66] = 255
    strokes = glyph_strokes(render)
    assert len(strokes) == 1


def test_a_dot_survives_as_a_point_stroke() -> None:
    render = _canvas()
    render[100:118, 60:68] = 255
    render[20:26, 61:67] = 255
    strokes = glyph_strokes(render)
    assert len(strokes) == 2
    assert min(len(stroke) for stroke in strokes) <= 2


def test_a_small_blob_becomes_a_tap() -> None:
    yy, xx = np.mgrid[:128, :128]
    render = _canvas()
    render[np.hypot(yy - 64, xx - 64) < 56] = 255
    strokes = glyph_strokes(render, extent_em=0.1)
    assert len(strokes) == 1 and len(strokes[0]) == 1
    assert np.allclose(strokes[0][0], [64, 64], atol=1)


def test_a_large_filled_shape_becomes_its_outline() -> None:
    render = _canvas()
    render[8:120, 8:120] = 255
    strokes = glyph_strokes(render, extent_em=0.7)
    assert len(strokes) == 1
    width, height = _stroke_extent(strokes[0])
    assert width > 100 and height > 100


def test_normalization_and_resampling() -> None:
    strokes = normalize_strokes([np.array([[10.0, 10.0], [30.0, 10.0]]), np.array([[20, 20.0]])])
    points = np.concatenate(strokes)
    assert np.ptp(points[:, 0]) == pytest.approx(1.0)
    assert points[:, 0].min() == pytest.approx(-0.5)
    resampled = resample(strokes[0], 0.1)
    assert len(resampled) == 11
    assert np.allclose(np.diff(resampled[:, 0]), 0.1)


def test_endpoint_changes_extend_or_trim_open_strokes() -> None:
    stroke = resample(np.array([[0.0, 0.0], [1.0, 0.0]]), 0.01)
    config = AugmentationConfig(endpoint_change=0.1)
    lengths = set()
    for seed in range(20):
        changed = change_endpoints(stroke, config, np.random.default_rng(seed), 0.01)
        lengths.add(round(float(np.ptp(changed[:, 0])), 2))
    assert min(lengths) < 1.0 < max(lengths)
    assert all(0.8 <= length <= 1.2 for length in lengths)


def test_corner_smoothing_rounds_a_corner_and_keeps_end_points() -> None:
    corner = resample(np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]), 0.01)
    smoothed = smooth_corners(corner, sigma=0.05, spacing=0.01, closed=False)
    assert smoothed.shape == corner.shape
    assert np.allclose(smoothed[0], corner[0]) and np.allclose(smoothed[-1], corner[-1])
    middle = len(corner) // 2
    assert np.hypot(*(smoothed[middle] - corner[middle])) > 0.01


def test_augmentation_is_deterministic_and_varies_with_the_seed() -> None:
    strokes = [
        np.array([[0.0, 0.0], [50.0, 100.0], [100.0, 0.0]]),
        np.array([[25.0, 50.0], [75, 50]]),
    ]
    config = AugmentationConfig()
    first = augment_strokes(strokes, config, np.random.default_rng(7))
    again = augment_strokes(strokes, config, np.random.default_rng(7))
    other = augment_strokes(strokes, config, np.random.default_rng(8))
    assert all(np.array_equal(a, b) for a, b in zip(first, again, strict=True))
    assert not all(np.array_equal(a, b) for a, b in zip(first, other, strict=True))
    points = np.concatenate(first)
    assert np.all(np.abs(points) < 1.0), "distortions stay moderate"


def test_pen_width_stays_in_range() -> None:
    config = AugmentationConfig()
    widths = [pen_width_for(64, config, np.random.default_rng(seed)) for seed in range(200)]
    low, high = config.pen_width_fraction
    assert min(widths) >= low * 64 - 1e-9 and max(widths) <= high * 64 + 1e-9


def test_stroke_table_round_trip() -> None:
    table = GlyphStrokeTable.from_stroke_lists(
        [[np.array([[0, 0], [1, 1]])], [], [np.array([[2, 2]]), np.array([[3, 3], [4, 4]])]]
    )
    assert len(table) == 3
    assert [table.stroke_count(row) for row in range(3)] == [1, 0, 2]
    assert table.strokes(2)[1].tolist() == [[3, 3], [4, 4]]


@pytest.mark.data
def test_real_generator_is_deterministic() -> None:
    strokes_dir = real_stage_dir_or_skip("glyphstrokes", GLYPH_STROKES_FILE)
    glyph_table = GlyphTable.load(real_stage_dir_or_skip("glyphs", "glyph_table.npz"))
    stroke_table = GlyphStrokeTable.load(strokes_dir / GLYPH_STROKES_FILE)
    assert len(stroke_table) == len(glyph_table.code_points)
    styles = {font_id: "sans" for font_id in glyph_table.font_ids}
    generator = SyntheticGenerator(stroke_table, glyph_table, styles, seed=3)
    first = generator.image(ord("A"), 0)
    assert first.shape == (64, 64) and first.max() == 255
    assert np.array_equal(first, generator.image(ord("A"), 0))
    assert not np.array_equal(first, generator.image(ord("A"), 1))
    assert len(generator.code_points) > 6000
