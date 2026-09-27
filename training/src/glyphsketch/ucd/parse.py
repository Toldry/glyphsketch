"""Parsers for the Unicode Character Database text formats used by the pipeline."""

import bisect
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from glyphsketch.ucd import files

# Name derivation rule NR2 (Unicode Standard, section 4.8): these ranges are named by a
# prefix followed by the code point in hex.
_RANGE_NAME_PREFIXES = {
    "CJK Ideograph": "CJK UNIFIED IDEOGRAPH-",
    "Tangut Ideograph": "TANGUT IDEOGRAPH-",
    "Jurchen Character": "JURCHEN CHARACTER-",
    "Seal Character": "SEAL CHARACTER-",
}

# Name derivation rule NR1 for precomposed Hangul syllables.
_HANGUL_SYLLABLE_BASE = 0xAC00
_HANGUL_SYLLABLE_COUNT = 11172
# fmt: off
_HANGUL_LEADING = [
    "G", "GG", "N", "D", "DD", "R", "M", "B", "BB", "S", "SS", "", "J", "JJ", "C", "K", "T",
    "P", "H",
]
_HANGUL_VOWELS = [
    "A", "AE", "YA", "YAE", "EO", "E", "YEO", "YE", "O", "WA", "WAE", "OE", "YO", "U", "WEO",
    "WE", "WI", "YU", "EU", "YI", "I",
]
_HANGUL_TRAILING = [
    "", "G", "GG", "GS", "N", "NJ", "NH", "D", "L", "LG", "LM", "LB", "LS", "LT", "LP", "LH",
    "M", "B", "BS", "S", "SS", "NG", "J", "C", "K", "T", "P", "H",
]
# fmt: on


def hangul_syllable_name(code_point: int) -> str:
    index = code_point - _HANGUL_SYLLABLE_BASE
    if not 0 <= index < _HANGUL_SYLLABLE_COUNT:
        raise ValueError(f"U+{code_point:04X} is not a precomposed Hangul syllable")
    leading = _HANGUL_LEADING[index // 588]
    vowel = _HANGUL_VOWELS[(index % 588) // 28]
    trailing = _HANGUL_TRAILING[index % 28]
    return f"HANGUL SYLLABLE {leading}{vowel}{trailing}"


def _data_lines(path: Path) -> Iterator[str]:
    """Yield the non-comment content of each line, stripped, skipping empty lines."""
    with path.open(encoding="utf-8-sig") as stream:
        for raw_line in stream:
            content = raw_line.split("#", 1)[0].strip()
            if content:
                yield content


def parse_code_point_range(text: str) -> tuple[int, int]:
    first, _, last = text.strip().partition("..")
    return int(first, 16), int(last or first, 16)


@dataclass(frozen=True)
class RangeValue:
    first: int
    last: int
    value: str


def parse_range_file(path: Path) -> list[RangeValue]:
    """Parse ``XXXX..YYYY ; value`` files (Blocks, Scripts, DerivedAge, PropList, ...)."""
    entries = []
    for line in _data_lines(path):
        fields = [field.strip() for field in line.split(";")]
        first, last = parse_code_point_range(fields[0])
        entries.append(RangeValue(first, last, fields[1]))
    return entries


class RangeLookup:
    """Maps a code point to the value of the range containing it (ranges must not overlap)."""

    def __init__(self, entries: list[RangeValue]) -> None:
        self._entries = sorted(entries, key=lambda entry: entry.first)
        self._starts = [entry.first for entry in self._entries]
        for previous, current in zip(self._entries, self._entries[1:], strict=False):
            if current.first <= previous.last:
                raise ValueError(f"Overlapping ranges at U+{current.first:04X}")

    def get(self, code_point: int) -> str | None:
        index = bisect.bisect_right(self._starts, code_point) - 1
        if index >= 0 and self._entries[index].last >= code_point:
            return self._entries[index].value
        return None

    def __iter__(self) -> Iterator[RangeValue]:
        return iter(self._entries)


def code_points_with_property(path: Path, property_name: str) -> frozenset[int]:
    """Code points listed with ``property_name`` in a binary-property file (PropList, emoji)."""
    code_points: set[int] = set()
    for entry in parse_range_file(path):
        if entry.value == property_name:
            code_points.update(range(entry.first, entry.last + 1))
    return frozenset(code_points)


@dataclass(frozen=True)
class UnicodeDataEntry:
    code_point: int
    name: str
    general_category: str
    decomposition: str
    simple_uppercase: int | None = None
    simple_lowercase: int | None = None


def parse_unicode_data(path: Path) -> dict[int, UnicodeDataEntry]:
    """Parse UnicodeData.txt, expanding ``<..., First>``/``<..., Last>`` ranges."""
    entries: dict[int, UnicodeDataEntry] = {}
    range_start: tuple[int, str] | None = None
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            fields = line.rstrip("\n").split(";")
            if len(fields) < 15:
                continue
            code_point = int(fields[0], 16)
            name, category, decomposition = fields[1], fields[2], fields[5]
            if name.endswith(", First>"):
                range_start = (code_point, name[1:].removesuffix(", First>"))
                continue
            if name.endswith(", Last>"):
                if range_start is None:
                    raise ValueError(f"Range end without start at U+{code_point:04X}")
                start, label = range_start
                for member in range(start, code_point + 1):
                    member_name = _range_member_name(label, member)
                    entries[member] = UnicodeDataEntry(member, member_name, category, "")
                range_start = None
                continue
            if name == "<control>":
                name = f"<control-{code_point:04X}>"
            entries[code_point] = UnicodeDataEntry(
                code_point,
                name,
                category,
                decomposition,
                simple_uppercase=int(fields[12], 16) if fields[12] else None,
                simple_lowercase=int(fields[13], 16) if fields[13] else None,
            )
    return entries


def _range_member_name(label: str, code_point: int) -> str:
    if label == "Hangul Syllable":
        return hangul_syllable_name(code_point)
    for label_start, prefix in _RANGE_NAME_PREFIXES.items():
        if label.startswith(label_start):
            return f"{prefix}{code_point:04X}"
    return f"<{label.lower()}-{code_point:04X}>"


def parse_script_aliases(path: Path) -> dict[str, str]:
    """Map short script codes (``Latn``) to long script names (``Latin``)."""
    aliases: dict[str, str] = {}
    for line in _data_lines(path):
        fields = [field.strip() for field in line.split(";")]
        if fields[0] == "sc":
            short_name, long_name = fields[1], fields[2]
            aliases[short_name] = long_name
            aliases[long_name] = long_name
            for extra in fields[3:]:
                aliases[extra] = long_name
    return aliases


def parse_script_extensions(path: Path, aliases: dict[str, str]) -> dict[int, tuple[str, ...]]:
    """Map code points to their Script_Extensions (long names), where the file lists any."""
    extensions: dict[int, tuple[str, ...]] = {}
    for entry in parse_range_file(path):
        scripts = tuple(sorted(aliases[short] for short in entry.value.split()))
        for code_point in range(entry.first, entry.last + 1):
            extensions[code_point] = scripts
    return extensions


@dataclass(frozen=True)
class ConfusableMapping:
    source: int
    target: tuple[int, ...]


def parse_confusables(path: Path) -> list[ConfusableMapping]:
    """Parse confusables.txt (``source ; target sequence ; MA``) or intentional.txt."""
    mappings = []
    for line in _data_lines(path):
        fields = [field.strip() for field in line.split(";")]
        source = int(fields[0], 16)
        target = tuple(int(part, 16) for part in fields[1].split())
        mappings.append(ConfusableMapping(source, target))
    return mappings


class UnicodeDatabase:
    """The subset of the UCD the pipeline needs, loaded from a downloaded UCD directory."""

    def __init__(self, ucd_dir: Path) -> None:
        self.ucd_dir = ucd_dir
        self.version = files.UNICODE_VERSION
        self.entries = parse_unicode_data(ucd_dir / files.UNICODE_DATA.relative_path)
        self.blocks = RangeLookup(parse_range_file(ucd_dir / files.BLOCKS.relative_path))
        self.scripts = RangeLookup(parse_range_file(ucd_dir / files.SCRIPTS.relative_path))
        self.ages = RangeLookup(parse_range_file(ucd_dir / files.DERIVED_AGE.relative_path))
        self.script_aliases = parse_script_aliases(
            ucd_dir / files.PROPERTY_VALUE_ALIASES.relative_path
        )
        self.script_extensions = parse_script_extensions(
            ucd_dir / files.SCRIPT_EXTENSIONS.relative_path, self.script_aliases
        )
        self.deprecated = code_points_with_property(
            ucd_dir / files.PROP_LIST.relative_path, "Deprecated"
        )
        self.emoji_presentation = code_points_with_property(
            ucd_dir / files.EMOJI_DATA.relative_path, "Emoji_Presentation"
        )

    def block_ranges(self) -> dict[str, tuple[int, int]]:
        return {entry.value: (entry.first, entry.last) for entry in self.blocks}

    def script_of(self, code_point: int) -> str:
        return self.scripts.get(code_point) or "Unknown"

    def script_extensions_of(self, code_point: int) -> tuple[str, ...]:
        return self.script_extensions.get(code_point, (self.script_of(code_point),))

    def general_category_of(self, code_point: int) -> str:
        entry = self.entries.get(code_point)
        return entry.general_category if entry else "Cn"
