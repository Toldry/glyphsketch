import json
from pathlib import Path

import numpy as np
import pytest

from conftest import real_stage_dir_or_skip
from font_fixture import TRIANGLE, WIDE_BAR, build_font, build_standard_test_font
from glyphsketch.charset import CHARSET_FILE_NAME, CharacterRecord, load_charset
from glyphsketch.fonts import FontManifest, FontSpec
from glyphsketch.glyphs import (
    COVERAGE_REPORT_FILE,
    GLYPHS_FILE,
    GlyphTable,
    load_renders,
    render_font,
    write_glyph_outputs,
)
from glyphsketch.render import CONTENT_SIZE, IMAGE_SIZE


def _record(code_point: int, block: str = "Test Block", emoji: bool = False) -> CharacterRecord:
    return CharacterRecord(
        code_point=code_point,
        char=chr(code_point),
        name=f"TEST {code_point:04X}",
        block=block,
        group="Test",
        script="Common",
        script_extensions=("Common",),
        general_category="So",
        age="1.1",
        emoji_presentation=emoji,
    )


def _spec(font_id: str) -> FontSpec:
    return FontSpec(
        id=font_id,
        family=font_id.title(),
        style="sans",
        sha256="0" * 64,
        license="OFL-1.1",
        license_sha256="0" * 64,
        url="file:///unused",
        license_url="file:///unused",
    )


def test_render_font_accepts_real_glyphs_and_counts_rejections(tmp_path: Path) -> None:
    font_path = build_standard_test_font(tmp_path / "test.ttf")
    result = render_font("test", font_path, [0x41, 0x2D, 0x42, 0x44, 0x100, 0x5D0])
    assert result.code_points == [0x41, 0x2D]
    assert result.images.shape == (2, IMAGE_SIZE, IMAGE_SIZE)
    assert dict(result.rejections) == {
        "empty outline": 1,
        "copy of .notdef": 1,
        "shared placeholder glyph": 1,
    }


def test_outputs_merge_fonts_and_drop_uncovered_characters(tmp_path: Path) -> None:
    fonts_dir = tmp_path / "fonts" / "files"
    fonts_dir.mkdir(parents=True)
    first = build_font(fonts_dir / "first.ttf", {"A": TRIANGLE}, {0x41: "A"})
    second = build_font(
        fonts_dir / "second.ttf", {"A": TRIANGLE, "hyphen": WIDE_BAR}, {0x41: "A", 0x2D: "hyphen"}
    )
    characters = [_record(0x2D), _record(0x41), _record(0x231A, emoji=True)]
    code_points = [record.code_point for record in characters]
    manifest = FontManifest("0" * 40, {}, (_spec("first"), _spec("second")))
    results = [render_font("second", second, code_points), render_font("first", first, code_points)]

    output_dir = tmp_path / "glyphs"
    output_dir.mkdir()
    summary = write_glyph_outputs(output_dir, characters, manifest, results)

    table = GlyphTable.load(output_dir)
    assert table.code_points.tolist() == [0x2D, 0x41, 0x41]
    assert [table.font_ids[index] for index in table.font_indices] == ["second", "first", "second"]
    renders = load_renders(output_dir)
    assert renders.shape == (3, IMAGE_SIZE, IMAGE_SIZE)
    assert all(renders[row].max() > 0 for row in range(3))
    assert table.rows_for(0x41).tolist() == [1, 2]
    assert summary["dropped_characters"] == [0x231A]
    saved = json.loads((output_dir / GLYPHS_FILE).read_text(encoding="utf-8"))
    assert saved["characters"] == [
        {"code_point": 0x2D, "fonts": ["second"]},
        {"code_point": 0x41, "fonts": ["first", "second"]},
    ]
    report = (output_dir / COVERAGE_REPORT_FILE).read_text(encoding="utf-8")
    assert "Emoji-presentation characters kept (text glyph in a text font): 0 of 1" in report
    assert "U+231A" in report


@pytest.mark.data
def test_real_glyph_renders() -> None:
    glyphs_dir = real_stage_dir_or_skip("glyphs", GLYPHS_FILE)
    table = GlyphTable.load(glyphs_dir)
    renders = load_renders(glyphs_dir)
    assert renders.shape[0] == table.code_points.shape[0] > 50_000
    charset = load_charset(real_stage_dir_or_skip("charset", CHARSET_FILE_NAME) / CHARSET_FILE_NAME)
    covered = set(table.code_points.tolist())
    assert covered <= {record.code_point for record in charset}
    for char, minimum_fonts in {"A": 30, "ж": 15, "א": 8, "ب": 5, "∑": 5, "★": 3, "⌚": 1}.items():
        assert len(table.rows_for(ord(char))) >= minimum_fonts, char
    rng = np.random.default_rng(0)
    for row in rng.choice(renders.shape[0], size=500, replace=False):
        image = np.asarray(renders[row])
        rows = np.flatnonzero(image.max(axis=1))
        columns = np.flatnonzero(image.max(axis=0))
        extent = max(rows[-1] - rows[0], columns[-1] - columns[0]) + 1
        assert abs(extent - CONTENT_SIZE) <= 2, f"row {row}"
