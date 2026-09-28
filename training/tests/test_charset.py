import json
from pathlib import Path

import pytest

from conftest import FIXTURES_DIR, real_stage_dir_or_skip
from glyphsketch.charset import (
    CHARSET_FILE_NAME,
    BlockGroup,
    CharsetConfig,
    CodePointOverride,
    UnknownBlockError,
    build_charset,
    format_code_point,
    load_charset,
    load_charset_config,
    parse_code_point,
    write_charset,
)
from glyphsketch.ucd.parse import UnicodeDatabase, parse_range_file

EXCLUDED_CATEGORIES = frozenset(["Cn", "Co", "Cc", "Cf", "Zs", "Zl", "Zp", "Cs", "Mn", "Me"])
# The real v0 config keeps combining marks (Mn, Me) since D34.
V0_EXCLUDED_CATEGORIES = frozenset(["Cn", "Co", "Cc", "Cf", "Zs", "Zl", "Zp", "Cs"])


def _fixture_config(**overrides: object) -> CharsetConfig:
    settings: dict[str, object] = {
        "name": "fixture",
        "groups": (
            BlockGroup(
                "Latin",
                (
                    "Basic Latin",
                    "Latin-1 Supplement",
                    "Latin Extended-A",
                    "Combining Diacritical Marks",
                ),
            ),
            BlockGroup("Greek", ("Greek and Coptic",)),
            BlockGroup("Hebrew", ("Hebrew",)),
            BlockGroup("Symbols", ("Miscellaneous Technical",)),
        ),
        "excluded_general_categories": EXCLUDED_CATEGORIES,
        "includes": (CodePointOverride(0xFDFC, "currency sign", "Symbols"),),
    }
    settings.update(overrides)
    return CharsetConfig(**settings)  # type: ignore[arg-type]


def test_code_point_notation_round_trips() -> None:
    assert parse_code_point("U+00e9") == 0xE9
    assert parse_code_point("0x1F600") == 0x1F600
    assert format_code_point(0x41) == "U+0041"
    assert format_code_point(0x1F600) == "U+1F600"


def test_builder_keeps_letters_and_symbols_and_drops_excluded_categories(
    fixture_ucd_dir: Path,
) -> None:
    build = build_charset(UnicodeDatabase(fixture_ucd_dir), _fixture_config())
    kept = {record.code_point for record in build.characters}
    assert kept == {0x41, 0x61, 0xB7, 0xE9, 0x391, 0x5D0, 0x231A, 0xFDFC}
    assert build.exclusion_counts["general category Cc"] == 1
    assert build.exclusion_counts["general category Zs"] == 1
    assert build.exclusion_counts["general category Cf"] == 1
    assert build.exclusion_counts["general category Mn"] == 1
    assert build.exclusion_counts["deprecated"] == 1
    assert build.exclusion_counts["general category Cn"] > 0


def test_records_carry_the_properties_later_stages_need(fixture_ucd_dir: Path) -> None:
    build = build_charset(UnicodeDatabase(fixture_ucd_dir), _fixture_config())
    records = {record.code_point: record for record in build.characters}
    watch = records[0x231A]
    assert watch.char == "⌚"
    assert watch.name == "WATCH"
    assert watch.block == "Miscellaneous Technical"
    assert watch.group == "Symbols"
    assert watch.emoji_presentation
    middle_dot = records[0xB7]
    assert middle_dot.script == "Common"
    assert middle_dot.script_extensions == ("Greek", "Latin")
    assert not middle_dot.emoji_presentation
    rial = records[0xFDFC]
    assert rial.block == "Arabic Presentation Forms-A"
    assert rial.script == "Arabic"
    assert rial.age == "3.2"


def test_explicit_exclusions_are_applied_and_counted(fixture_ucd_dir: Path) -> None:
    config = _fixture_config(excludes=(CodePointOverride(0xB7, "test"),))
    build = build_charset(UnicodeDatabase(fixture_ucd_dir), config)
    assert 0xB7 not in {record.code_point for record in build.characters}
    assert build.exclusion_counts["explicitly excluded"] == 1


def test_unknown_block_names_are_rejected(fixture_ucd_dir: Path) -> None:
    config = _fixture_config(groups=(BlockGroup("Latin", ("Basic Latin", "Latin Extended-Z")),))
    with pytest.raises(UnknownBlockError, match="Latin Extended-Z"):
        build_charset(UnicodeDatabase(fixture_ucd_dir), config)


def test_charset_file_round_trips(fixture_ucd_dir: Path, tmp_path: Path) -> None:
    build = build_charset(UnicodeDatabase(fixture_ucd_dir), _fixture_config())
    path = tmp_path / CHARSET_FILE_NAME
    write_charset(build, path)
    assert load_charset(path) == build.characters
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["unicode_version"] == "18.0.0"
    assert raw["character_count"] == len(build.characters)


def test_v0_config_names_only_real_unicode_18_blocks() -> None:
    config = load_charset_config()
    blocks_file = FIXTURES_DIR / "ucd/Blocks-18.0.0.txt"
    real_blocks = {entry.value for entry in parse_range_file(blocks_file)}
    assert set(config.blocks) <= real_blocks
    assert len(config.blocks) == len(set(config.blocks)), "a block is listed twice"
    assert config.excluded_general_categories == V0_EXCLUDED_CATEGORIES


@pytest.mark.data
def test_real_v0_charset() -> None:
    charset_dir = real_stage_dir_or_skip("charset", CHARSET_FILE_NAME)
    records = load_charset(charset_dir / CHARSET_FILE_NAME)
    by_code_point = {record.code_point: record for record in records}
    config = load_charset_config()
    assert 10000 < len(records) < 14000  # 12,205 candidates since D34
    # Since D34 also combining marks (acute, Hebrew patah, Arabic fatha), emoji and music.
    for included in "AzéßΩжאب∑→€ℝ①★✓𝔄\u0301\u05b7\u064e😀🚲𝄞":
        assert ord(included) in by_code_point, included
    # Zero-width space, no-break space, soft hyphen, ideographic space: never drawn.
    for excluded in "\u200b\u00a0\u00ad\u3000":
        assert ord(excluded) not in by_code_point, f"U+{ord(excluded):04X}"
    assert not {record.general_category for record in records} & V0_EXCLUDED_CATEGORIES
    allowed_blocks = set(config.blocks) | {"Arabic Presentation Forms-A"}
    assert {record.block for record in records} <= allowed_blocks
    assert by_code_point[ord("⌚")].emoji_presentation
    assert not by_code_point[ord("A")].emoji_presentation
