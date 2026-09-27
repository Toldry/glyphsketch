"""Confusable groups: characters that look the same once a drawing is size-normalized.

Candidate pairs come from three sources:

* Unicode's ``confusables.txt`` (UTS #39): two characters with the same skeleton;
* Unicode's ``intentional.txt``: pairs that are identical by design (Latin A, Greek Α);
* simple case pairs (c/C, o/O, ...), which size normalization makes identical for many
  letters but ``confusables.txt`` doesn't list.

Two characters end up in one group only if their glyphs really look alike in our renders.
``confusables.txt`` also links characters whose glyphs differ a lot (fraktur 𝔄 and A), and
putting those in one group would hide real recognition errors. Similarity is the
tolerant overlap of 32×32 ink masks: the fraction of each glyph's ink that lies within
one pixel of the other's ink, taking the smaller of the two fractions. It is computed per
font (both glyphs from the same font), and the median over fonts counts. Groups come from
complete-linkage clustering seeded by the candidate pairs, so every two members of a
group are at least ``SIMILARITY_THRESHOLD`` similar.
"""

import json
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from glyphsketch.charset import format_code_point
from glyphsketch.glyphs import GlyphTable
from glyphsketch.ucd import files
from glyphsketch.ucd.parse import UnicodeDatabase, parse_confusables

SIGNATURE_SIZE = 32
INK_THRESHOLD = 0.35
SIMILARITY_THRESHOLD = 0.85
MAX_RENDERS_PER_CHARACTER = 8
GROUPS_FILE = "groups.json"
REPORT_FILE = "confusable_groups.md"


def skeleton_candidates(ucd_dir: Path, code_points: set[int]) -> dict[tuple[int, int], str]:
    """Pairs of code points that share a confusables.txt skeleton or are intentional pairs."""
    pairs: dict[tuple[int, int], str] = {}
    mappings = parse_confusables(ucd_dir / files.CONFUSABLES.relative_path)
    skeleton = {mapping.source: mapping.target for mapping in mappings}
    by_skeleton: dict[tuple[int, ...], list[int]] = defaultdict(list)
    for code_point in code_points:
        by_skeleton[skeleton.get(code_point, (code_point,))].append(code_point)
    for members in by_skeleton.values():
        members.sort()
        for index, first in enumerate(members):
            for second in members[index + 1 :]:
                pairs[(first, second)] = "confusables"
    for mapping in parse_confusables(ucd_dir / files.INTENTIONAL_CONFUSABLES.relative_path):
        if len(mapping.target) != 1:
            continue
        pair = tuple(sorted((mapping.source, mapping.target[0])))
        if pair[0] != pair[1] and set(pair) <= code_points:
            pairs.setdefault((pair[0], pair[1]), "intentional")
    return pairs


def case_candidates(ucd: UnicodeDatabase, code_points: set[int]) -> dict[tuple[int, int], str]:
    pairs: dict[tuple[int, int], str] = {}
    for code_point in code_points:
        entry = ucd.entries.get(code_point)
        if entry is None:
            continue
        for other in (entry.simple_uppercase, entry.simple_lowercase):
            if other is not None and other != code_point and other in code_points:
                first, second = sorted((code_point, other))
                pairs.setdefault((first, second), "case")
    return pairs


def shape_signature(render: np.ndarray, size: int = SIGNATURE_SIZE) -> np.ndarray:
    """Boolean ink mask of a render, averaged down to ``size`` × ``size``."""
    image = np.asarray(render, dtype=np.float32) / 255.0
    factor = image.shape[0] // size
    pooled = image.reshape(size, factor, size, factor).mean(axis=(1, 3))
    return pooled > INK_THRESHOLD


def dilate(mask: np.ndarray) -> np.ndarray:
    """3×3 binary dilation."""
    padded = np.pad(mask, 1)
    grown = np.zeros_like(mask)
    for dy in range(3):
        for dx in range(3):
            grown |= padded[dy : dy + mask.shape[0], dx : dx + mask.shape[1]]
    return grown


def tolerant_similarity(
    first: np.ndarray,
    second: np.ndarray,
    first_dilated: np.ndarray | None = None,
    second_dilated: np.ndarray | None = None,
) -> float:
    first_ink, second_ink = first.sum(), second.sum()
    if first_ink == 0 or second_ink == 0:
        return 0.0
    first_dilated = dilate(first) if first_dilated is None else first_dilated
    second_dilated = dilate(second) if second_dilated is None else second_dilated
    first_covered = (first & second_dilated).sum() / first_ink
    second_covered = (second & first_dilated).sum() / second_ink
    return float(min(first_covered, second_covered))


@dataclass
class SignatureIndex:
    """Shape signatures (and their dilations) of every render, by code point and font."""

    signatures: dict[int, dict[str, tuple[np.ndarray, np.ndarray]]]
    cache: dict[tuple[int, int], float] = field(default_factory=dict)

    @classmethod
    def build(
        cls, renders: np.ndarray, table: GlyphTable, code_points: Iterable[int]
    ) -> "SignatureIndex":
        wanted = set(code_points)
        signatures: dict[int, dict[str, tuple[np.ndarray, np.ndarray]]] = defaultdict(dict)
        for row, code_point in enumerate(table.code_points.tolist()):
            if code_point in wanted:
                font_id = table.font_ids[table.font_indices[row]]
                signature = shape_signature(renders[row])
                signatures[code_point][font_id] = (signature, dilate(signature))
        return cls(dict(signatures))

    def similarity(self, first: int, second: int) -> float:
        """Median similarity over the fonts that have both glyphs (over font pairs if none
        has both). The median asks whether the glyphs look alike in a typical font; the
        maximum would let one unusual font decide."""
        key = (min(first, second), max(first, second))
        if key in self.cache:
            return self.cache[key]
        first_fonts = self.signatures.get(first, {})
        second_fonts = self.signatures.get(second, {})
        common = sorted(set(first_fonts) & set(second_fonts))
        if common:
            pairs = [(first_fonts[font], second_fonts[font]) for font in common]
        else:
            pairs = [
                (a, b)
                for a in list(first_fonts.values())[:MAX_RENDERS_PER_CHARACTER]
                for b in list(second_fonts.values())[:MAX_RENDERS_PER_CHARACTER]
            ]
        values = [tolerant_similarity(a[0], b[0], a[1], b[1]) for a, b in pairs]
        result = float(np.median(values)) if values else 0.0
        self.cache[key] = result
        return result


def complete_linkage_groups(
    candidates: Sequence[tuple[int, int]],
    similarity: Callable[[int, int], float],
    threshold: float,
) -> list[list[int]]:
    """Agglomerative clustering restricted to candidate pairs, with complete linkage.

    Candidate pairs are visited from most to least similar; the clusters of a pair are
    merged only if every pair of characters across the two clusters is at least
    ``threshold`` similar. Unlike connected components, this cannot chain dissimilar
    characters together through a series of look-alikes (6 - б - о - O).
    """
    scored = sorted(
        ((similarity(first, second), first, second) for first, second in candidates),
        reverse=True,
    )
    cluster_of: dict[int, int] = {}
    members: dict[int, list[int]] = {}
    for score, first, second in scored:
        if score < threshold:
            break
        for code_point in (first, second):
            if code_point not in cluster_of:
                cluster_of[code_point] = code_point
                members[code_point] = [code_point]
        first_cluster, second_cluster = cluster_of[first], cluster_of[second]
        if first_cluster == second_cluster:
            continue
        if all(
            similarity(a, b) >= threshold
            for a in members[first_cluster]
            for b in members[second_cluster]
        ):
            keep, absorb = sorted((first_cluster, second_cluster))
            for code_point in members[absorb]:
                cluster_of[code_point] = keep
            members[keep].extend(members.pop(absorb))
    return sorted((sorted(group) for group in members.values()), key=lambda group: group[0])


@dataclass(frozen=True)
class ConfusableGroups:
    groups: list[list[int]]
    """Groups with at least two members, each sorted by code point."""

    def group_of(self) -> dict[int, int]:
        """Map each grouped code point to the smallest code point of its group."""
        return {member: group[0] for group in self.groups for member in group}

    def representative(self, code_point: int, group_of: dict[int, int] | None = None) -> int:
        mapping = group_of if group_of is not None else self.group_of()
        return mapping.get(code_point, code_point)

    @classmethod
    def load(cls, path: Path) -> "ConfusableGroups":
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(groups=[list(group) for group in raw["groups"]])


def build_confusable_groups(
    ucd: UnicodeDatabase,
    renders: np.ndarray,
    table: GlyphTable,
    threshold: float = SIMILARITY_THRESHOLD,
) -> tuple[ConfusableGroups, list[dict[str, Any]]]:
    """Return the groups and every candidate pair with its similarity and decision."""
    code_points = set(table.code_points.tolist())
    candidates = skeleton_candidates(ucd.ucd_dir, code_points)
    for pair, source in case_candidates(ucd, code_points).items():
        candidates.setdefault(pair, source)
    index = SignatureIndex.build(renders, table, {cp for pair in candidates for cp in pair})
    groups = [
        group
        for group in complete_linkage_groups(sorted(candidates), index.similarity, threshold)
        if len(group) > 1
    ]
    group_of = {member: group[0] for group in groups for member in group}
    pairs = []
    for (first, second), source in sorted(candidates.items()):
        similarity = index.similarity(first, second)
        same_group = first in group_of and group_of.get(first) == group_of.get(second)
        pairs.append(
            {"pair": [first, second], "source": source, "similarity": round(similarity, 3),
             "kept": similarity >= threshold, "grouped": same_group}
        )  # fmt: skip
    return ConfusableGroups(groups), pairs


def write_groups(
    output_dir: Path,
    groups: ConfusableGroups,
    pairs: Sequence[dict[str, Any]],
    names: dict[int, str],
    threshold: float = SIMILARITY_THRESHOLD,
) -> None:
    payload = {"threshold": threshold, "groups": groups.groups, "pairs": list(pairs)}
    (output_dir / GROUPS_FILE).write_text(json.dumps(payload) + "\n", encoding="utf-8")
    (output_dir / REPORT_FILE).write_text(
        groups_report(groups, pairs, names, threshold), encoding="utf-8"
    )


def groups_report(
    groups: ConfusableGroups,
    pairs: Sequence[dict[str, Any]],
    names: dict[int, str],
    threshold: float,
) -> str:
    by_source: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for pair in pairs:
        counts = by_source[pair["source"]]
        counts[0] += 1
        counts[1] += int(pair["grouped"])
        counts[2] += int(not pair["kept"])
    sizes = [len(group) for group in groups.groups]
    lines = [
        "# Confusable groups",
        "",
        "Generated by the `confusables` pipeline stage (see `glyphsketch/confusables.py`).",
        "Candidate pairs come from `confusables.txt`, `intentional.txt` and case pairs.",
        "Complete-linkage clustering keeps two characters in one group only if every pair",
        f"of members has a glyph similarity (median tolerant overlap) of at least {threshold}.",
        "",
        f"- Groups: {len(groups.groups)}, covering {sum(sizes)} characters "
        f"(largest: {max(sizes, default=0)})",
        "",
        "| Candidate source | Candidate pairs | Ended up in one group | Glyphs differ |",
        "|------------------|----------------:|----------------------:|--------------:|",
    ]
    for source, (total, grouped, rejected) in sorted(by_source.items()):
        lines.append(f"| {source} | {total} | {grouped} | {rejected} |")
    lines += ["", "## Groups", ""]
    for group in sorted(groups.groups, key=len, reverse=True):
        chars = " ".join(chr(code_point) for code_point in group)
        codes = ", ".join(format_code_point(code_point) for code_point in group)
        lines.append(f"- {chars} ({codes})")
    lines += ["", "## Examples of rejected candidates", ""]
    rejected_pairs = sorted(
        (pair for pair in pairs if not pair["kept"]), key=lambda pair: pair["similarity"]
    )
    step = max(1, len(rejected_pairs) // 60)
    for pair in rejected_pairs[::step][:60]:
        first, second = pair["pair"]
        lines.append(
            f"- {chr(first)} / {chr(second)}: {pair['similarity']:.2f} ({pair['source']}; "
            f"{names.get(first, '?')} / {names.get(second, '?')})"
        )
    return "\n".join(lines) + "\n"
