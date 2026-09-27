from pathlib import Path

import numpy as np
import pytest

from font_fixture import build_standard_test_font
from glyphsketch.render import CONTENT_SIZE, IMAGE_SIZE, GlyphChecker, GlyphRenderer


@pytest.fixture
def test_font(tmp_path: Path) -> Path:
    return build_standard_test_font(tmp_path / "test.ttf")


def _ink_extent(image: np.ndarray) -> tuple[int, int, int, int]:
    rows = np.flatnonzero(image.max(axis=1))
    columns = np.flatnonzero(image.max(axis=0))
    return int(rows[0]), int(rows[-1]), int(columns[0]), int(columns[-1])


@pytest.mark.parametrize(
    ("code_point", "reason"),
    [
        (0x41, None),
        (0x2D, None),
        (0x42, "empty outline"),
        (0x44, "copy of .notdef"),
        (0x105, "shared placeholder glyph"),
        (0x5D0, "not in cmap"),
    ],
)
def test_checker_rejects_everything_that_is_not_a_real_glyph(
    test_font: Path, code_point: int, reason: str | None
) -> None:
    assert GlyphChecker(test_font).rejection_reason(code_point) == reason


def test_checker_rejects_explicit_mappings_to_notdef(test_font: Path) -> None:
    checker = GlyphChecker(test_font)
    checker.cmap[0x43] = ".notdef"
    assert checker.rejection_reason(0x43) == "maps to .notdef"


def test_render_fills_the_content_box_and_is_centered(test_font: Path) -> None:
    render = GlyphRenderer(test_font).render("A")
    assert render is not None
    assert render.image.shape == (IMAGE_SIZE, IMAGE_SIZE)
    assert render.image.dtype == np.uint8
    top, bottom, left, right = _ink_extent(render.image)
    height, width = bottom - top + 1, right - left + 1
    assert abs(max(height, width) - CONTENT_SIZE) <= 1
    assert abs((top + bottom) / 2 - (IMAGE_SIZE - 1) / 2) <= 1
    assert abs((left + right) / 2 - (IMAGE_SIZE - 1) / 2) <= 1
    assert render.image.max() == 255


def test_render_keeps_the_aspect_ratio(test_font: Path) -> None:
    render = GlyphRenderer(test_font).render("-")
    assert render is not None
    top, bottom, left, right = _ink_extent(render.image)
    width, height = right - left + 1, bottom - top + 1
    assert abs(width - CONTENT_SIZE) <= 1
    assert height == pytest.approx(CONTENT_SIZE * 100 / 900, abs=2)


def test_render_reports_the_ink_box_in_em_units(test_font: Path) -> None:
    render = GlyphRenderer(test_font).render("A")
    assert render is not None
    left, bottom, right, top = render.ink_box_em
    assert left == pytest.approx(0.1, abs=0.01)
    assert bottom == pytest.approx(0.0, abs=0.01)
    assert right == pytest.approx(0.5, abs=0.01)
    assert top == pytest.approx(0.7, abs=0.01)


def test_render_of_an_empty_glyph_returns_none(test_font: Path) -> None:
    assert GlyphRenderer(test_font).render("B") is None
