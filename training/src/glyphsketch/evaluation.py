"""Top-k accuracy of a recognizer on real drawings.

A recognizer ranks candidate code points for each drawing. Every test sample is scored
four ways: top-1 and top-5, each plain (the label itself must appear) and
confusable-aware (any member of the label's confusable group counts). Results are
reported overall, by dataset, by Unicode block and by character subset ("seen" characters
have real training data; "zero-shot" ones only synthetic, see ``realdata.splits``).

Overall accuracy is given both per sample (micro) and averaged over characters (macro),
because a few symbols (∫, ∑, α) make up a large share of the Detexify samples.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

import numpy as np

from glyphsketch.realdata.samples import SampleSet
from glyphsketch.strokes import Drawing

TOP_K = 5


class Recognizer(Protocol):
    def rank(self, drawings: Sequence[Drawing], k: int) -> np.ndarray:
        """Return an (len(drawings), k) array of code points, best first."""
        ...


@dataclass(frozen=True)
class Hits:
    """Per-sample hit flags."""

    top1: np.ndarray
    top5: np.ndarray
    top1_confusable: np.ndarray
    top5_confusable: np.ndarray


def score_predictions(
    predictions: np.ndarray, labels: np.ndarray, group_of: dict[int, int]
) -> Hits:
    predictions = np.asarray(predictions)
    labels = np.asarray(labels)
    if predictions.shape[0] != labels.shape[0] or predictions.shape[1] < TOP_K:
        raise ValueError(f"Need an (N, >= {TOP_K}) prediction array for N labels")
    exact = predictions[:, :TOP_K] == labels[:, None]
    representative = np.vectorize(lambda cp: group_of.get(int(cp), int(cp)), otypes=[np.int64])
    grouped = representative(predictions[:, :TOP_K]) == representative(labels)[:, None]
    return Hits(
        top1=exact[:, 0],
        top5=exact.any(axis=1),
        top1_confusable=grouped[:, 0],
        top5_confusable=grouped.any(axis=1),
    )


@dataclass(frozen=True)
class Metrics:
    samples: int
    characters: int
    top1: float
    top5: float
    top1_confusable: float
    top5_confusable: float

    @classmethod
    def of(cls, hits: Hits, mask: np.ndarray, labels: np.ndarray) -> "Metrics":
        count = int(mask.sum())
        if count == 0:
            return cls(0, 0, float("nan"), float("nan"), float("nan"), float("nan"))
        return cls(
            samples=count,
            characters=len(set(labels[mask].tolist())),
            top1=float(hits.top1[mask].mean()),
            top5=float(hits.top5[mask].mean()),
            top1_confusable=float(hits.top1_confusable[mask].mean()),
            top5_confusable=float(hits.top5_confusable[mask].mean()),
        )

    @classmethod
    def macro(cls, hits: Hits, mask: np.ndarray, labels: np.ndarray) -> "Metrics":
        """Mean over characters of each character's accuracy."""
        per_character: dict[int, list[int]] = defaultdict(list)
        for index in np.flatnonzero(mask):
            per_character[int(labels[index])].append(int(index))
        if not per_character:
            return cls.of(hits, mask, labels)
        averages = {
            name: float(
                np.mean([getattr(hits, name)[rows].mean() for rows in per_character.values()])
            )
            for name in ("top1", "top5", "top1_confusable", "top5_confusable")
        }
        return cls(samples=int(mask.sum()), characters=len(per_character), **averages)


@dataclass
class EvaluationReport:
    recognizer: str
    overall: Metrics
    overall_macro: Metrics
    by_dataset: dict[str, Metrics] = field(default_factory=dict)
    by_subset: dict[str, Metrics] = field(default_factory=dict)
    by_block: dict[str, Metrics] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "recognizer": self.recognizer,
            "overall": asdict(self.overall),
            "overall_macro": asdict(self.overall_macro),
            "by_dataset": {name: asdict(metrics) for name, metrics in self.by_dataset.items()},
            "by_subset": {name: asdict(metrics) for name, metrics in self.by_subset.items()},
            "by_block": {name: asdict(metrics) for name, metrics in self.by_block.items()},
            "notes": self.notes,
        }


def evaluate_predictions(
    recognizer_name: str,
    predictions: np.ndarray,
    samples: SampleSet,
    zero_shot: np.ndarray,
    block_of: dict[int, str],
    group_of: dict[int, int],
) -> EvaluationReport:
    labels = samples.code_points.astype(np.int64)
    hits = score_predictions(predictions, labels, group_of)
    everything = np.ones(len(labels), dtype=bool)
    report = EvaluationReport(
        recognizer=recognizer_name,
        overall=Metrics.of(hits, everything, labels),
        overall_macro=Metrics.macro(hits, everything, labels),
    )
    for dataset in sorted(set(samples.datasets.tolist())):
        report.by_dataset[dataset] = Metrics.of(hits, samples.datasets == dataset, labels)
    report.by_subset["seen"] = Metrics.of(hits, ~zero_shot, labels)
    report.by_subset["zero-shot"] = Metrics.of(hits, zero_shot, labels)
    blocks = np.array([block_of.get(int(cp), "?") for cp in labels])
    for block in sorted(set(blocks.tolist()), key=lambda name: -int((blocks == name).sum())):
        report.by_block[block] = Metrics.of(hits, blocks == block, labels)
    return report


def evaluate(
    recognizer: Recognizer,
    recognizer_name: str,
    samples: SampleSet,
    zero_shot: np.ndarray,
    block_of: dict[int, str],
    group_of: dict[int, int],
    batch_size: int = 512,
) -> EvaluationReport:
    predictions = []
    for start in range(0, len(samples), batch_size):
        drawings = [
            samples.strokes(index) for index in range(start, min(start + batch_size, len(samples)))
        ]
        predictions.append(recognizer.rank(drawings, TOP_K))
    stacked = np.concatenate(predictions) if predictions else np.zeros((0, TOP_K), np.int64)
    return evaluate_predictions(recognizer_name, stacked, samples, zero_shot, block_of, group_of)


def _percent(value: float) -> str:
    return "–" if np.isnan(value) else f"{100 * value:.1f}"


def metrics_row(label: str, metrics: Metrics) -> str:
    return (
        f"| {label} | {metrics.samples} | {metrics.characters} | {_percent(metrics.top1)} | "
        f"{_percent(metrics.top5)} | {_percent(metrics.top1_confusable)} | "
        f"{_percent(metrics.top5_confusable)} |"
    )


METRICS_HEADER = (
    "| Slice | Samples | Characters | Top-1 | Top-5 | Top-1 (conf.) | Top-5 (conf.) |\n"
    "|-------|--------:|-----------:|------:|------:|--------------:|--------------:|"
)


def report_markdown(report: EvaluationReport, max_blocks: int = 40) -> str:
    lines = [f"### {report.recognizer}", "", METRICS_HEADER]
    lines.append(metrics_row("All (per sample)", report.overall))
    lines.append(metrics_row("All (per character)", report.overall_macro))
    for name, metrics in report.by_subset.items():
        lines.append(metrics_row(f"Characters: {name}", metrics))
    for name, metrics in report.by_dataset.items():
        lines.append(metrics_row(f"Dataset: {name}", metrics))
    lines += ["", "By Unicode block (per sample):", "", METRICS_HEADER]
    for name, metrics in list(report.by_block.items())[:max_blocks]:
        lines.append(metrics_row(name, metrics))
    lines += [f"- {note}" for note in report.notes]
    return "\n".join(lines) + "\n"
