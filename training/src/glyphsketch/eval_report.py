"""Evaluate recognizers on the real test set and write EVAL.md.

Each evaluating stage saves one JSON report per recognizer in ``$DATA_DIR/evaluations/``.
The ``evalreport`` stage renders all of them into ``EVAL.md`` at the repository root, so
EVAL.md always reflects the latest runs.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from glyphsketch.charset import CHARSET_FILE_NAME, load_charset
from glyphsketch.confusables import GROUPS_FILE, ConfusableGroups
from glyphsketch.evaluation import (
    METRICS_HEADER,
    EvaluationReport,
    Metrics,
    Recognizer,
    evaluate,
    metrics_row,
)
from glyphsketch.paths import data_dir
from glyphsketch.realdata.build import SAMPLES_FILE
from glyphsketch.realdata.samples import SampleSet
from glyphsketch.realdata.splits import held_out_mask, zero_shot_mask

EVALUATIONS_DIR_NAME = "evaluations"


@dataclass(frozen=True)
class TestSet:
    samples: SampleSet
    zero_shot: np.ndarray
    block_of: dict[int, str]
    group_of: dict[int, int]

    @classmethod
    def load(cls, realdata_dir: Path, charset_dir: Path, confusables_dir: Path) -> "TestSet":
        everything = SampleSet.load(realdata_dir / SAMPLES_FILE)
        held_out = np.flatnonzero(held_out_mask(everything))
        samples = everything.subset(held_out)
        characters = load_charset(charset_dir / CHARSET_FILE_NAME)
        groups = ConfusableGroups.load(confusables_dir / GROUPS_FILE)
        return cls(
            samples=samples,
            zero_shot=zero_shot_mask(samples),
            block_of={record.code_point: record.block for record in characters},
            group_of=groups.group_of(),
        )


def evaluations_dir() -> Path:
    directory = data_dir() / EVALUATIONS_DIR_NAME
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def run_and_save(
    recognizer: Recognizer, name: str, slug: str, test_set: TestSet, notes: list[str]
) -> EvaluationReport:
    report = evaluate(
        recognizer, name, test_set.samples, test_set.zero_shot, test_set.block_of,
        test_set.group_of,
    )  # fmt: skip
    report.notes.extend(notes)
    payload = report.to_json() | {"slug": slug, "evaluated_at": _now()}
    (evaluations_dir() / f"{slug}.json").write_text(
        json.dumps(payload, indent=1) + "\n", encoding="utf-8"
    )
    return report


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _metrics(raw: dict[str, Any]) -> Metrics:
    return Metrics(**raw)


def _pct(value: float) -> str:
    return f"{100 * value:.1f}%"


def _by_slug(reports: list[dict[str, Any]], slug: str) -> dict[str, Any] | None:
    return next((report for report in reports if report["slug"] == slug), None)


def _package_description(package: dict[str, Any] | None) -> str:
    if package is None:
        return "int8"
    return f"{package['characters']:,} characters, {package['shipped_bytes'] / 1e6:.1f} MB, int8"


def headline_section(
    reports: list[dict[str, Any]], package: dict[str, Any] | None = None
) -> list[str]:
    tiles, ranked = _by_slug(reports, "export-tiles"), _by_slug(reports, "export-ranked")
    hog = _by_slug(reports, "hog")
    if tiles is None or ranked is None:
        return []
    t, r = _metrics(tiles["overall"]), _metrics(ranked["overall"])
    seen = _metrics(tiles["by_subset"]["seen"])
    zero = _metrics(tiles["by_subset"]["zero-shot"])
    lines = [
        "## Results at a glance",
        "",
        f"The shipped package (`export/`, {_package_description(package)}) on held-out writers:",
        "",
        f"- **Result tiles** (one per look-alike group, as the demo shows them): the right "
        f"group is among the first five tiles for **{_pct(t.top5_confusable)}** of drawings, "
        f"and the first tile shows exactly the drawn character for {_pct(t.top1)}.",
        f"- **Ranked characters**: top-1 {_pct(r.top1)}, top-5 {_pct(r.top5)} "
        f"({_pct(r.top5_confusable)} counting look-alikes).",
        f"- **Zero-shot characters**, which have no real handwriting in training, reach "
        f"{_pct(zero.top5_confusable)} tile top-5, against {_pct(seen.top5_confusable)} for "
        "characters with real training drawings. Adding a character with only a font works.",
    ]
    if hog is not None:
        h = _metrics(hog["overall"])
        lines.append(
            f"- The best trivial baseline (HOG nearest glyph) reaches {_pct(h.top5_confusable)} "
            "top-5 counting look-alikes."
        )
    lines += [
        "",
        "How the choices were made (DECISIONS.md): synthetic + real training beats synthetic",
        "only, also on zero-shot characters (D29); one index vector per font beats averaged",
        "or synthetic prototypes (D22, D29); the frequency prior adds about 4 points of top-1",
        "(D25, D26); PCA to 48 dimensions and int8 cost nothing (D27).",
        "",
    ]
    return lines


def blocks_section(reports: list[dict[str, Any]], minimum_samples: int = 100) -> list[str]:
    tiles = _by_slug(reports, "export-tiles")
    if tiles is None:
        return []
    blocks = [
        (name, _metrics(raw))
        for name, raw in tiles["by_block"].items()
        if raw["samples"] >= minimum_samples
    ]
    blocks.sort(key=lambda item: item[1].top5_confusable)
    header = [
        "| Block | Samples | Characters | Tile top-5 (conf.) | Exact top-1 |",
        "|-------|--------:|-----------:|-------------------:|------------:|",
    ]

    def rows(items: list[tuple[str, Metrics]]) -> list[str]:
        return [
            f"| {name} | {m.samples} | {m.characters} | {_pct(m.top5_confusable)} "
            f"| {_pct(m.top1)} |"
            for name, m in items
        ]

    return [
        "## Where it works and where it doesn't",
        "",
        f"Unicode blocks with at least {minimum_samples} test drawings, shipped package, tiles.",
        "",
        "Weakest:",
        "",
        *header,
        *rows(blocks[:6]),
        "",
        "Strongest:",
        "",
        *header,
        *rows(blocks[::-1][:6]),
        "",
        "Two causes are visible in the weakest blocks. Geometric Shapes holds filled and",
        "outlined versions of the same shape (■ □, ● ○), which a pen drawing doesn't",
        "distinguish, and small and large ones (▪ ■, ◦ ○), which size normalization makes",
        "identical. The styled alphabets (Mathematical Alphanumeric Symbols, Letterlike",
        "Symbols: 𝒜, 𝔄, ℬ) are drawn by people as plain letters, while their glyphs keep the",
        "font's style. The full per-block tables are in the detailed results below.",
        "",
    ]


def comparison_section(comparison: dict[str, Any] | None) -> list[str]:
    if comparison is None:
        return []
    reports = comparison["reports"]
    lines = [
        "## Comparison with Detypify",
        "",
        "[Detypify](https://github.com/QuarticCat/detypify) (MIT) is an open-source recognizer",
        f"of {comparison['symbols']} Typst symbols: a classifier over a fixed set, where",
        f"glyphsketch retrieves among {comparison['index_characters']:,} characters. Of the "
        "test drawings, "
        f"{comparison['eligible_samples']:,} have a label among Detypify's symbols (nearly all "
        f"from Detexify); both recognizers run on the same fixed random sample of "
        f"{comparison['test_samples']:,} of them ({comparison['test_characters']} characters; "
        "standard error about 0.6 points).",
        "",
        "| Recognizer | Top-1 | Top-5 | Top-1 (conf.) | Top-5 (conf.) |",
        "|------------|------:|------:|--------------:|--------------:|",
    ]
    for key in ("detypify", "glyphsketch-restricted", "glyphsketch", "glyphsketch-tiles"):
        report = reports[key]
        m = _metrics(report["overall"])
        lines.append(
            f"| {report['recognizer']} | {_pct(m.top1)} | {_pct(m.top5)} | "
            f"{_pct(m.top1_confusable)} | {_pct(m.top5_confusable)} |"
        )
    detypify = _metrics(reports["detypify"]["overall"])
    restricted = _metrics(reports["glyphsketch-restricted"]["overall"])
    lines += [
        "",
        f"On its own symbols Detypify is ahead: with the same {comparison['symbols']} "
        f"candidates, its top-1 is {_pct(detypify.top1)} against {_pct(restricted.top1)}, "
        f"and top-5 {_pct(detypify.top5)} against {_pct(restricted.top5)}. A classifier "
        "trained on real drawings of a fixed set is the right tool for that set. glyphsketch "
        f"covers {comparison['index_characters'] / comparison['symbols']:.0f} times as many "
        "characters, most of which have no handwriting data at all,",
        "and adding one needs only a font; searching all of them costs it accuracy on these",
        "symbols (the third row).",
    ]
    lines += [
        "",
        "**Warning: possible overlap.** Detypify is trained on Detexify's data, and these test",
        "drawings come from Detexify users. Nothing indicates that its training excluded our",
        "test writers, so its numbers here may be optimistic. glyphsketch never trained on",
        "these writers (D16).",
        "",
        "Detypify's input was reproduced from its `drawStrokes` (224 px canvas, 8 px lines);",
        "the lines are drawn with our anti-aliased rasterizer rather than a browser canvas,",
        "which is close but not identical (`training/src/glyphsketch/detypify.py`).",
        "",
    ]
    return lines


LIMITATIONS = [
    "## Limitations",
    "",
    "- **The test mix is mostly maths symbols.** Detexify provides 93% of the test drawings",
    "  (drawn in its web page); UJI (letters, digits, punctuation) and Omniglot (non-Latin",
    "  alphabets) add the rest. Finger drawings on a phone keyboard may differ; the demo's",
    "  labelled-drawing export is the way to measure that.",
    "- **Drawings are compared by shape only.** Size and position are normalized away, so",
    "  case pairs such as o/O or c/C, and pairs like the letter o and the digit 0 in some",
    "  fonts, can only be told apart by the tile's menu.",
    "- **No stroke order.** The recognizer sees the image, not the pen's path (PLAN.md,",
    "  section 1), so it cannot use the order people write strokes in.",
    "- **No real handwriting of the characters added in D34.** Emoji, music symbols,",
    "  combining marks, box drawing, braille and the other added blocks are measured only",
    "  on synthetic drawings (DECISIONS.md, D34); the test set above has almost none.",
    "- **Characters outside the fonts are out of reach**, and CJK is excluded (D35).",
    "",
]


def render_eval_markdown(
    reports: list[dict[str, Any]],
    test_summary: str,
    comparison: dict[str, Any] | None = None,
    package: dict[str, Any] | None = None,
) -> str:
    lines = [
        "# Evaluation",
        "",
        "Generated by the `evalreport` pipeline stage from the latest runs; do not edit by hand.",
        f"Last generated: {_now()}.",
        "",
        *headline_section(reports, package),
        *comparison_section(comparison),
        *blocks_section(reports),
        *LIMITATIONS,
        "## Test data",
        "",
        test_summary,
        "",
        "Metrics: top-1 and top-5 accuracy per test sample. *Conf.* (confusable-aware)",
        "counts a prediction as correct when it is in the label's confusable group",
        "(`docs/reports/confusable_groups.md`), e.g. Latin A for a Greek Α. *Seen* characters",
        "have real training data; *zero-shot* characters are seen in training only as",
        "synthetic drawings (the baselines use no training data at all).",
        "",
        "## Summary",
        "",
        "| Recognizer | Top-1 | Top-5 | Top-1 (conf.) | Top-5 (conf.) | Top-5 (conf.), zero-shot "
        "| Top-5 (conf.), per character |",
        "|------------|------:|------:|--------------:|--------------:|--------------------------:"
        "|-----------------------------:|",
    ]
    for report in reports:
        overall = _metrics(report["overall"])
        zero_shot = _metrics(report["by_subset"]["zero-shot"])
        macro = _metrics(report["overall_macro"])
        lines.append(
            f"| {report['recognizer']} | {100 * overall.top1:.1f} | {100 * overall.top5:.1f} | "
            f"{100 * overall.top1_confusable:.1f} | {100 * overall.top5_confusable:.1f} | "
            f"{100 * zero_shot.top5_confusable:.1f} | {100 * macro.top5_confusable:.1f} |"
        )
    lines += ["", "## Detailed results"]
    for report in reports:
        lines += ["", f"<details><summary>{report['recognizer']}</summary>", ""]
        lines += [f"{note}" for note in report.get("notes", [])]
        lines += ["", METRICS_HEADER]
        lines.append(metrics_row("All (per sample)", _metrics(report["overall"])))
        lines.append(metrics_row("All (per character)", _metrics(report["overall_macro"])))
        for name, raw in report["by_subset"].items():
            lines.append(metrics_row(f"Characters: {name}", _metrics(raw)))
        for name, raw in report["by_dataset"].items():
            lines.append(metrics_row(f"Dataset: {name}", _metrics(raw)))
        lines += ["", "<details><summary>By Unicode block</summary>", "", METRICS_HEADER]
        for name, raw in report["by_block"].items():
            lines.append(metrics_row(name, _metrics(raw)))
        lines += ["", "</details>", "", "</details>"]
    return "\n".join(lines) + "\n"


def test_data_summary(test_set: TestSet) -> str:
    samples = test_set.samples
    lines = [
        "| Dataset | Test samples | Characters | Zero-shot samples |",
        "|---------|-------------:|-----------:|------------------:|",
    ]
    for dataset in sorted(set(samples.datasets.tolist())):
        mask = samples.datasets == dataset
        lines.append(
            f"| {dataset} | {int(mask.sum())} | {len(set(samples.code_points[mask].tolist()))} | "
            f"{int((mask & test_set.zero_shot).sum())} |"
        )
    lines.append(
        f"| **all** | {len(samples)} | {len(set(samples.code_points.tolist()))} | "
        f"{int(test_set.zero_shot.sum())} |"
    )
    lines += [
        "",
        "Test samples come from held-out writers (DECISIONS.md, D16). Details of the data",
        "are in `docs/reports/real_data.md`.",
    ]
    return "\n".join(lines)


REPORT_ORDER = ("export-", "pixels", "hog", "encoder-")
RUN_ORDER = ("-1701-", "-long-")


def report_order(slug: str) -> tuple[int, int, str]:
    """The shipped package first, then the baselines, then the encoder runs: the
    equal-step ablation pair before the long runs."""
    kind = next((rank for rank, prefix in enumerate(REPORT_ORDER) if slug.startswith(prefix)), 9)
    run = next((rank for rank, marker in enumerate(RUN_ORDER) if marker in slug), 9)
    return kind, run, slug


def load_saved_reports() -> list[dict[str, Any]]:
    reports = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(evaluations_dir().glob("*.json"))
    ]
    return sorted(reports, key=lambda report: report_order(report["slug"]))
