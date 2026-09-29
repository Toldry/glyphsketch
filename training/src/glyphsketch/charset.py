"""Build the candidate character set from the Unicode Character Database.

The result (``charset.json``) lists every code point the recognizer may return, with the
properties later stages need: name, block, script, general category, the Unicode version
that introduced it and whether it defaults to emoji presentation.
"""

import json
import tomllib
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from glyphsketch.paths import RESOURCES_DIR
from glyphsketch.ucd.parse import UnicodeDatabase

DEFAULT_CONFIG_PATH = RESOURCES_DIR / "charset_v0.toml"
CHARSET_FILE_NAME = "charset.json"


def parse_code_point(text: str) -> int:
    """Parse ``U+00E9``, ``0x00E9`` or ``00E9`` into an integer code point."""
    cleaned = text.strip().upper().removeprefix("U+").removeprefix("0X")
    return int(cleaned, 16)


def format_code_point(code_point: int) -> str:
    return f"U+{code_point:04X}"


@dataclass(frozen=True)
class BlockGroup:
    name: str
    blocks: tuple[str, ...]
    # Join existing look-alike groups instead of shaping them (confusables, D40): a large
    # set of added scripts full of circles and strokes would otherwise split groups such
    # as o/O under complete linkage.
    join_lookalikes: bool = False


@dataclass(frozen=True)
class CodePointOverride:
    code_point: int
    reason: str
    group: str = ""


@dataclass(frozen=True)
class CharsetConfig:
    name: str
    groups: tuple[BlockGroup, ...]
    excluded_general_categories: frozenset[str]
    exclude_deprecated: bool = True
    excluded_scripts: frozenset[str] = frozenset()
    includes: tuple[CodePointOverride, ...] = ()
    excludes: tuple[CodePointOverride, ...] = ()

    @property
    def blocks(self) -> tuple[str, ...]:
        return tuple(block for group in self.groups for block in group.blocks)


def load_charset_config(path: Path = DEFAULT_CONFIG_PATH) -> CharsetConfig:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    return CharsetConfig(
        name=raw["name"],
        groups=tuple(
            BlockGroup(
                name=group["name"],
                blocks=tuple(group["blocks"]),
                join_lookalikes=group.get("join_lookalikes", False),
            )
            for group in raw["group"]
        ),
        excluded_general_categories=frozenset(raw["excluded_general_categories"]),
        exclude_deprecated=raw.get("exclude_deprecated", True),
        excluded_scripts=frozenset(raw.get("excluded_scripts", [])),
        includes=tuple(
            CodePointOverride(parse_code_point(item["code_point"]), item["reason"], item["group"])
            for item in raw.get("include", [])
        ),
        excludes=tuple(
            CodePointOverride(parse_code_point(item["code_point"]), item["reason"])
            for item in raw.get("exclude", [])
        ),
    )


@dataclass(frozen=True)
class CharacterRecord:
    code_point: int
    char: str
    name: str
    block: str
    group: str
    script: str
    script_extensions: tuple[str, ...]
    general_category: str
    age: str
    emoji_presentation: bool


@dataclass
class CharsetBuild:
    config_name: str
    unicode_version: str
    characters: list[CharacterRecord]
    exclusion_counts: Counter[str] = field(default_factory=Counter)

    def to_json(self) -> dict[str, Any]:
        return {
            "charset": self.config_name,
            "unicode_version": self.unicode_version,
            "character_count": len(self.characters),
            "counts_by_block": dict(Counter(record.block for record in self.characters)),
            "counts_by_general_category": dict(
                sorted(Counter(record.general_category for record in self.characters).items())
            ),
            "exclusion_counts": dict(sorted(self.exclusion_counts.items())),
            "characters": [asdict(record) for record in self.characters],
        }


class UnknownBlockError(ValueError):
    pass


def exclusion_reason(ucd: UnicodeDatabase, config: CharsetConfig, code_point: int) -> str | None:
    """Why ``code_point`` is left out of the charset, or None if it stays."""
    category = ucd.general_category_of(code_point)
    if category in config.excluded_general_categories:
        return f"general category {category}"
    if config.exclude_deprecated and code_point in ucd.deprecated:
        return "deprecated"
    script = ucd.script_of(code_point)
    if script in config.excluded_scripts:
        return f"script {script}"
    return None


def build_charset(ucd: UnicodeDatabase, config: CharsetConfig) -> CharsetBuild:
    block_ranges = ucd.block_ranges()
    unknown_blocks = [block for block in config.blocks if block not in block_ranges]
    if unknown_blocks:
        raise UnknownBlockError(f"Blocks not in Unicode {ucd.version}: {unknown_blocks}")

    candidate_groups: dict[int, str] = {}
    for group in config.groups:
        for block in group.blocks:
            first, last = block_ranges[block]
            for code_point in range(first, last + 1):
                candidate_groups[code_point] = group.name
    for include in config.includes:
        candidate_groups[include.code_point] = include.group
    explicit_excludes = {override.code_point for override in config.excludes}

    build = CharsetBuild(config_name=config.name, unicode_version=ucd.version, characters=[])
    for code_point in sorted(candidate_groups):
        reason = exclusion_reason(ucd, config, code_point)
        if reason is None and code_point in explicit_excludes:
            reason = "explicitly excluded"
        if reason is not None:
            build.exclusion_counts[reason] += 1
            continue
        build.characters.append(
            CharacterRecord(
                code_point=code_point,
                char=chr(code_point),
                name=ucd.entries[code_point].name,
                block=ucd.blocks.get(code_point) or "No_Block",
                group=candidate_groups[code_point],
                script=ucd.script_of(code_point),
                script_extensions=ucd.script_extensions_of(code_point),
                general_category=ucd.general_category_of(code_point),
                age=ucd.ages.get(code_point) or "unassigned",
                emoji_presentation=code_point in ucd.emoji_presentation,
            )
        )
    return build


def write_charset(build: CharsetBuild, path: Path) -> None:
    path.write_text(
        json.dumps(build.to_json(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


def load_charset(path: Path) -> list[CharacterRecord]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    records = []
    for item in raw["characters"]:
        item["script_extensions"] = tuple(item["script_extensions"])
        records.append(CharacterRecord(**item))
    return records
