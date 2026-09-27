"""Render single characters from a font into normalized grayscale bitmaps.

Two separate checks keep bad glyphs out:

* ``GlyphChecker`` reads the font with fontTools and rejects code points that are not in
  the cmap, map to ``.notdef``, have an empty outline, or reuse the ``.notdef`` outline.
  Pillow only ever draws with the one font it is given (no fallback), so a character that
  passes this check is drawn from its own glyph.
* ``GlyphRenderer`` draws the glyph and rejects renders without ink.

Normalization: the ink bounding box is scaled, keeping its aspect ratio, so that its longer
side is ``CONTENT_SIZE`` pixels, and centered in an ``IMAGE_SIZE`` square. The glyph is
re-rendered at the size that produces that scale, so outlines stay sharp instead of being
resampled. The drawing preprocessing (M5, M9) uses the same box, so glyphs and drawings
are framed identically.
"""

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

IMAGE_SIZE = 128
CONTENT_SIZE = 112
PROBE_EM_PIXELS = 256
MAX_EM_PIXELS = 4096
REGULAR_WEIGHT = 400.0
# More code points than this sharing one glyph suggests a placeholder glyph.
MAX_CODE_POINTS_PER_GLYPH = 8

Outline = tuple[tuple[str, tuple[object, ...]], ...]


class GlyphChecker:
    """Decides from the font file alone whether a code point has a real glyph."""

    def __init__(self, font_path: Path) -> None:
        self.font = TTFont(font_path, lazy=True)
        self.cmap: dict[int, str] = self.font.getBestCmap() or {}
        self.glyph_set = self.font.getGlyphSet()
        self.glyph_order = self.font.getGlyphOrder()
        self.notdef_outline = self._outline(self.glyph_order[0])
        self.code_points_per_glyph = Counter(self.cmap.values())

    def _outline(self, glyph_name: str) -> Outline:
        pen = DecomposingRecordingPen(self.glyph_set)
        self.glyph_set[glyph_name].draw(pen)
        return tuple((operator, tuple(arguments)) for operator, arguments in pen.value)

    def rejection_reason(self, code_point: int) -> str | None:
        """Why the font has no usable glyph for ``code_point``, or None if it has one."""
        glyph_name = self.cmap.get(code_point)
        if glyph_name is None:
            return "not in cmap"
        if glyph_name == self.glyph_order[0] or glyph_name == ".notdef":
            return "maps to .notdef"
        if self.code_points_per_glyph[glyph_name] > MAX_CODE_POINTS_PER_GLYPH:
            return "shared placeholder glyph"
        outline = self._outline(glyph_name)
        if not any(operator in ("lineTo", "curveTo", "qCurveTo") for operator, _ in outline):
            return "empty outline"
        if outline == self.notdef_outline:
            return "copy of .notdef"
        return None


@dataclass(frozen=True)
class GlyphRender:
    image: np.ndarray
    """uint8 array (IMAGE_SIZE, IMAGE_SIZE); 0 is paper, 255 is ink."""
    ink_box_em: tuple[float, float, float, float]
    """Ink bounding box (left, bottom, right, top) in em units, origin on the baseline, y up."""


def _variation_values(font: ImageFont.FreeTypeFont, weight: float) -> list[float] | None:
    try:
        axes = font.get_variation_axes()
    except OSError:
        return None
    values = []
    for axis in axes:
        raw_name = axis["name"]
        name = raw_name.decode() if isinstance(raw_name, bytes) else str(raw_name)
        value = float(axis["default"] or 0)
        if name.lower() == "weight":
            minimum, maximum = float(axis["minimum"] or 0), float(axis["maximum"] or 0)
            value = min(max(weight, minimum), maximum)
        values.append(value)
    return values


class GlyphRenderer:
    """Draws characters from one font file at its regular weight."""

    def __init__(self, font_path: Path, weight: float = REGULAR_WEIGHT) -> None:
        self.font_path = font_path
        self.weight = weight
        self._fonts: dict[int, ImageFont.FreeTypeFont] = {}

    def _font(self, em_pixels: int) -> ImageFont.FreeTypeFont:
        font = self._fonts.get(em_pixels)
        if font is None:
            font = ImageFont.truetype(
                str(self.font_path), em_pixels, layout_engine=ImageFont.Layout.BASIC
            )
            values = _variation_values(font, self.weight)
            if values is not None:
                font.set_variation_by_axes(values)
            if len(self._fonts) > 64:
                self._fonts.clear()
            self._fonts[em_pixels] = font
        return font

    def _draw(self, char: str, em_pixels: int) -> tuple[np.ndarray, int, int] | None:
        """Draw ``char``; return the ink crop and its top-left position relative to the origin."""
        font = self._font(em_pixels)
        left, top, right, bottom = font.getbbox(char, anchor="ls")
        padding = 4 + em_pixels // 16
        width = int(right - left) + 2 * padding
        height = int(bottom - top) + 2 * padding
        canvas = Image.new("L", (max(width, 1), max(height, 1)), 0)
        origin_x, origin_y = padding - int(left), padding - int(top)
        ImageDraw.Draw(canvas).text((origin_x, origin_y), char, font=font, fill=255, anchor="ls")
        pixels = np.asarray(canvas)
        rows = np.flatnonzero(pixels.max(axis=1))
        columns = np.flatnonzero(pixels.max(axis=0))
        if rows.size == 0:
            return None
        crop = pixels[rows[0] : rows[-1] + 1, columns[0] : columns[-1] + 1]
        return crop, int(columns[0]) - origin_x, int(rows[0]) - origin_y

    def render(self, char: str) -> GlyphRender | None:
        """Render ``char`` normalized to the standard box, or None if it has no ink."""
        probe = self._draw(char, PROBE_EM_PIXELS)
        if probe is None:
            return None
        probe_crop, probe_x, probe_y = probe
        probe_height, probe_width = probe_crop.shape
        ink_box_em = (
            probe_x / PROBE_EM_PIXELS,
            -(probe_y + probe_height) / PROBE_EM_PIXELS,
            (probe_x + probe_width) / PROBE_EM_PIXELS,
            -probe_y / PROBE_EM_PIXELS,
        )
        scale = CONTENT_SIZE / max(probe_width, probe_height)
        em_pixels = round(PROBE_EM_PIXELS * scale)
        em_pixels = min(max(em_pixels, 8), MAX_EM_PIXELS)
        final = self._draw(char, em_pixels)
        if final is None:
            return None
        crop = final[0]
        crop_height, crop_width = crop.shape
        if max(crop_height, crop_width) != CONTENT_SIZE:
            fit = CONTENT_SIZE / max(crop_height, crop_width)
            size = (max(1, round(crop_width * fit)), max(1, round(crop_height * fit)))
            crop = np.asarray(Image.fromarray(crop).resize(size, Image.Resampling.LANCZOS))
            crop_height, crop_width = crop.shape
        image = np.zeros((IMAGE_SIZE, IMAGE_SIZE), dtype=np.uint8)
        top = (IMAGE_SIZE - crop_height) // 2
        left = (IMAGE_SIZE - crop_width) // 2
        image[top : top + crop_height, left : left + crop_width] = crop
        return GlyphRender(image=image, ink_box_em=ink_box_em)
