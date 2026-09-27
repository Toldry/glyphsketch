"""Build tiny TrueType fonts in tests, so font code can be tested without downloads."""

from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

UNITS_PER_EM = 1000
ASCENT = 800
DESCENT = -200

Contour = list[tuple[int, int]]

BOX_WITH_HOLE: list[Contour] = [
    [(50, 0), (50, 700), (450, 700), (450, 0)],
    [(100, 50), (400, 50), (400, 650), (100, 650)],
]
TRIANGLE: list[Contour] = [[(100, 0), (300, 700), (500, 0)]]
WIDE_BAR: list[Contour] = [[(0, 300), (0, 400), (900, 400), (900, 300)]]


def build_font(
    path: Path,
    glyph_contours: dict[str, list[Contour]],
    character_map: dict[int, str],
) -> Path:
    """Write a TrueType font whose ``.notdef`` is ``BOX_WITH_HOLE`` plus the given glyphs."""
    glyph_order = [".notdef", *glyph_contours]
    shapes = {".notdef": BOX_WITH_HOLE, **glyph_contours}
    builder = FontBuilder(UNITS_PER_EM, isTTF=True)
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap(character_map)
    glyphs = {}
    metrics = {}
    for name in glyph_order:
        pen = TTGlyphPen(None)
        for contour in shapes[name]:
            pen.moveTo(contour[0])
            for point in contour[1:]:
                pen.lineTo(point)
            pen.closePath()
        glyphs[name] = pen.glyph()
        left_side_bearing = min((x for contour in shapes[name] for x, _ in contour), default=0)
        metrics[name] = (1000, left_side_bearing)
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics(metrics)
    builder.setupHorizontalHeader(ascent=ASCENT, descent=DESCENT)
    builder.setupNameTable({"familyName": "Glyphsketch Test", "styleName": "Regular"})
    builder.setupOS2(
        sTypoAscender=ASCENT, sTypoDescender=DESCENT, usWinAscent=ASCENT, usWinDescent=-DESCENT
    )
    builder.setupPost()
    builder.save(str(path))
    return path


def build_standard_test_font(path: Path) -> Path:
    """A font exercising every rejection rule of ``GlyphChecker``.

    * U+0041 A: a triangle (accepted)
    * U+002D -: a wide bar (accepted)
    * U+0042 B: an empty glyph
    * U+0044 D: a separate glyph with the same outline as ``.notdef``
    * U+0100..U+0109: ten code points sharing one placeholder glyph

    fontTools drops cmap entries that point at ``.notdef`` when it compiles a font, so tests
    of that rule add such an entry to ``GlyphChecker.cmap`` directly.
    """
    character_map = {0x41: "A", 0x2D: "hyphen", 0x42: "B", 0x44: "D"}
    character_map.update({code_point: "placeholder" for code_point in range(0x100, 0x10A)})
    return build_font(
        path,
        {
            "A": TRIANGLE,
            "hyphen": WIDE_BAR,
            "B": [],
            "D": BOX_WITH_HOLE,
            "placeholder": TRIANGLE,
        },
        character_map,
    )
