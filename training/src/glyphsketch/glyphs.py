"""Render every charset character from every manifest font that has a real glyph for it.

Outputs of the ``glyphs`` stage:

* ``renders.npy``: uint8 array (N, IMAGE_SIZE, IMAGE_SIZE), one normalized render per
  (character, font) pair, sorted by code point, then by manifest font order.
* ``glyph_table.npz``: per render, its code point, font index and ink box in em units.
* ``glyphs.json``: the fonts, the covered characters with their fonts, the dropped
  characters and the rejection counts per font.
* ``coverage_report.md``: coverage per block and per font, in Markdown.

A character without at least one accepted render is dropped. This is also where the
emoji rule applies (DECISIONS.md, D8): the manifest has only text fonts, so an
Emoji_Presentation character survives only if a text font has a glyph for it.
"""

import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from glyphsketch.charset import CharacterRecord, format_code_point
from glyphsketch.fonts import FontManifest, font_file_path
from glyphsketch.parallel import default_workers, single_threaded_pool
from glyphsketch.render import CONTENT_SIZE, IMAGE_SIZE, GlyphChecker, GlyphRenderer

RENDERS_FILE = "renders.npy"
GLYPH_TABLE_FILE = "glyph_table.npz"
GLYPHS_FILE = "glyphs.json"
COVERAGE_REPORT_FILE = "coverage_report.md"
EXAMPLES_PER_REASON = 12


@dataclass
class FontRenderResult:
    font_id: str
    code_points: list[int]
    images: np.ndarray
    ink_boxes: list[tuple[float, float, float, float]]
    rejections: Counter[str] = field(default_factory=Counter)
    rejected_examples: dict[str, list[int]] = field(default_factory=dict)


def render_font(font_id: str, font_path: Path, code_points: Sequence[int]) -> FontRenderResult:
    """Render the given code points from one font, skipping those without a real glyph."""
    checker = GlyphChecker(font_path)
    renderer = GlyphRenderer(font_path)
    accepted: list[int] = []
    images: list[np.ndarray] = []
    ink_boxes: list[tuple[float, float, float, float]] = []
    rejections: Counter[str] = Counter()
    examples: dict[str, list[int]] = defaultdict(list)

    def reject(code_point: int, reason: str) -> None:
        rejections[reason] += 1
        if len(examples[reason]) < EXAMPLES_PER_REASON:
            examples[reason].append(code_point)

    for code_point in code_points:
        if code_point not in checker.cmap:
            continue
        reason = checker.rejection_reason(code_point)
        if reason is not None:
            reject(code_point, reason)
            continue
        render = renderer.render(chr(code_point))
        if render is None:
            reject(code_point, "renders blank")
            continue
        accepted.append(code_point)
        images.append(render.image)
        ink_boxes.append(render.ink_box_em)
    stacked = np.stack(images) if images else np.zeros((0, IMAGE_SIZE, IMAGE_SIZE), dtype=np.uint8)
    return FontRenderResult(font_id, accepted, stacked, ink_boxes, rejections, dict(examples))


def _render_font_task(arguments: tuple[str, Path, list[int]]) -> FontRenderResult:
    return render_font(*arguments)


def render_all_fonts(
    characters: Sequence[CharacterRecord],
    manifest: FontManifest,
    fonts_dir: Path,
    workers: int | None = None,
) -> list[FontRenderResult]:
    code_points = [record.code_point for record in characters]
    tasks = [(spec.id, font_file_path(fonts_dir, spec), code_points) for spec in manifest.fonts]
    workers = workers or default_workers(len(tasks))
    if workers <= 1:
        return [_render_font_task(task) for task in tasks]
    with single_threaded_pool(workers) as pool:
        return pool.map(_render_font_task, tasks, chunksize=1)


@dataclass(frozen=True)
class GlyphTable:
    """Which (code point, font) each row of ``renders.npy`` shows."""

    code_points: np.ndarray
    font_indices: np.ndarray
    ink_boxes_em: np.ndarray
    font_ids: tuple[str, ...]

    @classmethod
    def load(cls, glyphs_dir: Path) -> "GlyphTable":
        with np.load(glyphs_dir / GLYPH_TABLE_FILE) as table:
            return cls(
                code_points=table["code_points"],
                font_indices=table["font_indices"],
                ink_boxes_em=table["ink_boxes_em"],
                font_ids=tuple(str(font_id) for font_id in table["font_ids"]),
            )

    def rows_for(self, code_point: int) -> np.ndarray:
        return np.flatnonzero(self.code_points == code_point)


def load_renders(glyphs_dir: Path, *, memory_map: bool = True) -> np.ndarray:
    renders: np.ndarray = np.load(glyphs_dir / RENDERS_FILE, mmap_mode="r" if memory_map else None)
    return renders


def write_glyph_outputs(
    output_dir: Path,
    characters: Sequence[CharacterRecord],
    manifest: FontManifest,
    results: Sequence[FontRenderResult],
) -> dict[str, Any]:
    """Merge the per-font results, write all stage outputs and return the summary."""
    font_order = {spec.id: index for index, spec in enumerate(manifest.fonts)}
    rows: list[tuple[int, int, int, int]] = []
    for result_index, result in enumerate(results):
        font_index = font_order[result.font_id]
        for position, code_point in enumerate(result.code_points):
            rows.append((code_point, font_index, result_index, position))
    rows.sort()

    renders = np.lib.format.open_memmap(
        output_dir / RENDERS_FILE,
        mode="w+",
        dtype=np.uint8,
        shape=(len(rows), IMAGE_SIZE, IMAGE_SIZE),
    )
    ink_boxes = np.zeros((len(rows), 4), dtype=np.float32)
    for row, (_, _, result_index, position) in enumerate(rows):
        renders[row] = results[result_index].images[position]
        ink_boxes[row] = results[result_index].ink_boxes[position]
    renders.flush()
    del renders
    np.savez(
        output_dir / GLYPH_TABLE_FILE,
        code_points=np.array([row[0] for row in rows], dtype=np.int32),
        font_indices=np.array([row[1] for row in rows], dtype=np.int16),
        ink_boxes_em=ink_boxes,
        font_ids=np.array([spec.id for spec in manifest.fonts]),
    )

    fonts_by_code_point: dict[int, list[str]] = defaultdict(list)
    for code_point, font_index, _, _ in rows:
        fonts_by_code_point[code_point].append(manifest.fonts[font_index].id)
    covered = [record for record in characters if record.code_point in fonts_by_code_point]
    dropped = [record for record in characters if record.code_point not in fonts_by_code_point]
    summary: dict[str, Any] = {
        "image_size": IMAGE_SIZE,
        "content_size": CONTENT_SIZE,
        "render_count": len(rows),
        "fonts": [
            {"id": spec.id, "family": spec.family, "style": spec.style, "license": spec.license}
            for spec in manifest.fonts
        ],
        "characters": [
            {"code_point": record.code_point, "fonts": fonts_by_code_point[record.code_point]}
            for record in covered
        ],
        "dropped_characters": [record.code_point for record in dropped],
        "rejections": {
            result.font_id: {
                reason: {
                    "count": count,
                    "examples": [
                        format_code_point(code_point)
                        for code_point in result.rejected_examples[reason]
                    ],
                }
                for reason, count in sorted(result.rejections.items())
            }
            for result in results
            if result.rejections
        },
    }
    (output_dir / GLYPHS_FILE).write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    report = coverage_report(characters, manifest, results, fonts_by_code_point)
    (output_dir / COVERAGE_REPORT_FILE).write_text(report, encoding="utf-8")
    return summary


def coverage_report(
    characters: Sequence[CharacterRecord],
    manifest: FontManifest,
    results: Sequence[FontRenderResult],
    fonts_by_code_point: dict[int, list[str]],
) -> str:
    """Markdown coverage report: per block, per font, and the dropped characters."""
    by_block: dict[str, list[CharacterRecord]] = defaultdict(list)
    for record in characters:
        by_block[record.block].append(record)
    covered_count = sum(1 for record in characters if record.code_point in fonts_by_code_point)
    render_count = sum(len(fonts) for fonts in fonts_by_code_point.values())
    emoji = [record for record in characters if record.emoji_presentation]
    emoji_kept = [record for record in emoji if record.code_point in fonts_by_code_point]

    lines = [
        "# Glyph coverage",
        "",
        "Generated by the `glyphs` pipeline stage. A character counts as covered by a font",
        "when the font maps it to a glyph that is not `.notdef`, not empty, not a copy of",
        "`.notdef`, not a placeholder shared by many code points, and renders with ink.",
        "",
        f"- Candidate characters (charset stage): {len(characters)}",
        f"- Covered by at least one font: {covered_count}",
        f"- Dropped (no font has a real glyph): {len(characters) - covered_count}",
        f"- Renders (character, font pairs): {render_count}, "
        f"{render_count / max(covered_count, 1):.1f} per covered character",
        f"- Emoji-presentation characters kept (text glyph in a text font): "
        f"{len(emoji_kept)} of {len(emoji)}",
        "",
        "## By block",
        "",
        "| Block | Candidates | Covered | 3+ fonts | Median fonts | Dropped |",
        "|-------|-----------:|--------:|---------:|-------------:|--------:|",
    ]
    for block, records in by_block.items():
        counts = [len(fonts_by_code_point.get(record.code_point, [])) for record in records]
        covered = sum(1 for count in counts if count > 0)
        lines.append(
            f"| {block} | {len(records)} | {covered} | {sum(1 for c in counts if c >= 3)} | "
            f"{int(np.median(counts))} | {len(records) - covered} |"
        )
    lines += [
        "",
        "## By font",
        "",
        "| Font | Style | License | Rendered | Rejected |",
        "|------|-------|---------|---------:|----------|",
    ]
    results_by_font = {result.font_id: result for result in results}
    for spec in manifest.fonts:
        result = results_by_font.get(spec.id)
        if result is None:
            continue
        rejected = ", ".join(f"{reason}: {n}" for reason, n in sorted(result.rejections.items()))
        lines.append(
            f"| {spec.family} | {spec.style} | {spec.license} | {len(result.code_points)} | "
            f"{rejected or '-'} |"
        )
    lines += ["", "## Dropped characters", ""]
    dropped_by_block: dict[str, list[CharacterRecord]] = defaultdict(list)
    for record in characters:
        if record.code_point not in fonts_by_code_point:
            dropped_by_block[record.block].append(record)
    if not dropped_by_block:
        lines.append("None.")
    for block, records in dropped_by_block.items():
        ages = Counter(record.age for record in records)
        age_text = ", ".join(f"{age}: {n}" for age, n in sorted(ages.items()))
        listed = " ".join(format_code_point(record.code_point) for record in records[:40])
        more = f" … and {len(records) - 40} more" if len(records) > 40 else ""
        lines.append(f"- **{block}** ({len(records)}; by Unicode version: {age_text}): ")
        lines.append(f"  {listed}{more}")
    return "\n".join(lines) + "\n"
