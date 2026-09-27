import unicodedata
from pathlib import Path

import pytest

from conftest import real_stage_dir_or_skip
from glyphsketch.ucd.parse import (
    RangeLookup,
    RangeValue,
    UnicodeDatabase,
    code_points_with_property,
    hangul_syllable_name,
    parse_code_point_range,
    parse_confusables,
    parse_unicode_data,
)


def test_parse_code_point_range_accepts_single_code_points_and_ranges() -> None:
    assert parse_code_point_range("0041") == (0x41, 0x41)
    assert parse_code_point_range(" 1F600..1F64F ") == (0x1F600, 0x1F64F)


@pytest.mark.parametrize(
    ("code_point", "name"),
    [
        (0xAC00, "HANGUL SYLLABLE GA"),
        (0xAC01, "HANGUL SYLLABLE GAG"),
        (0xC544, "HANGUL SYLLABLE A"),
        (0xD7A3, "HANGUL SYLLABLE HIH"),
    ],
)
def test_hangul_syllable_names_follow_rule_nr1(code_point: int, name: str) -> None:
    assert hangul_syllable_name(code_point) == name


def test_unicode_data_expands_named_ranges(fixture_ucd_dir: Path) -> None:
    entries = parse_unicode_data(fixture_ucd_dir / "ucd/UnicodeData.txt")
    assert entries[0x41].name == "LATIN CAPITAL LETTER A"
    assert entries[0x41].general_category == "Lu"
    assert entries[0x00E9].decomposition == "0065 0301"
    assert entries[0x0000].name == "<control-0000>"
    assert entries[0x4E01].name == "CJK UNIFIED IDEOGRAPH-4E01"
    assert entries[0xAC00].name == "HANGUL SYLLABLE GA"
    assert entries[0xD7A3].name == "HANGUL SYLLABLE HIH"
    assert entries[0xE123].general_category == "Co"
    assert 0x0042 not in entries


def test_range_lookup_finds_the_containing_range() -> None:
    lookup = RangeLookup([RangeValue(0x80, 0xFF, "Latin-1"), RangeValue(0x00, 0x7F, "ASCII")])
    assert lookup.get(0x41) == "ASCII"
    assert lookup.get(0xFF) == "Latin-1"
    assert lookup.get(0x100) is None


def test_range_lookup_rejects_overlaps() -> None:
    with pytest.raises(ValueError, match="Overlapping"):
        RangeLookup([RangeValue(0x00, 0x7F, "a"), RangeValue(0x70, 0xFF, "b")])


def test_binary_property_file_with_byte_order_mark(fixture_ucd_dir: Path) -> None:
    emoji = code_points_with_property(
        fixture_ucd_dir / "ucd/emoji/emoji-data.txt", "Emoji_Presentation"
    )
    assert emoji == {0x231A, 0x231B}


def test_database_resolves_scripts_and_script_extensions(fixture_ucd_dir: Path) -> None:
    ucd = UnicodeDatabase(fixture_ucd_dir)
    assert ucd.script_of(0x41) == "Latin"
    assert ucd.script_extensions_of(0x41) == ("Latin",)
    assert ucd.script_extensions_of(0xB7) == ("Greek", "Latin")
    assert ucd.script_of(0x0250) == "Unknown"
    assert ucd.general_category_of(0x0250) == "Cn"
    assert ucd.blocks.get(0x05D0) == "Hebrew"
    assert ucd.ages.get(0xFDFC) == "3.2"
    assert 0x0149 in ucd.deprecated


def test_parse_confusables_handles_sequences_and_byte_order_mark(tmp_path: Path) -> None:
    path = tmp_path / "confusables.txt"
    path.write_text(
        "﻿# confusables.txt\n"
        "0391 ;\t0041 ;\tMA\t# ( Α → A ) GREEK CAPITAL LETTER ALPHA → LATIN CAPITAL LETTER A\n"
        "2474 ;\t0028 0031 0029 ;\tMA\t# ( ⑴ → (1) )\n",
        encoding="utf-8",
    )
    mappings = parse_confusables(path)
    assert [(mapping.source, mapping.target) for mapping in mappings] == [
        (0x0391, (0x41,)),
        (0x2474, (0x28, 0x31, 0x29)),
    ]


# General categories that changed between Python's Unicode 15.0 and the pinned version.
CATEGORY_CHANGES_SINCE_UNICODE_15 = {0x0295: "Lo", 0x1171E: "Mc"}


@pytest.mark.data
def test_real_database_matches_python_unicodedata() -> None:
    ucd = UnicodeDatabase(real_stage_dir_or_skip("ucd", "ucd/UnicodeData.txt"))
    assert len(ucd.entries) > 150_000
    compared = 0
    for code_point, entry in ucd.entries.items():
        expected_name = unicodedata.name(chr(code_point), None)
        if expected_name is None:
            continue
        assert entry.name == expected_name, f"U+{code_point:04X}"
        expected_category = CATEGORY_CHANGES_SINCE_UNICODE_15.get(
            code_point, unicodedata.category(chr(code_point))
        )
        assert entry.general_category == expected_category, f"U+{code_point:04X}"
        compared += 1
    assert compared > 140_000
