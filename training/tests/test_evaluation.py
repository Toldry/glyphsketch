from collections.abc import Sequence

import numpy as np
import pytest

from glyphsketch.evaluation import (
    Metrics,
    evaluate,
    evaluate_predictions,
    report_markdown,
    score_predictions,
)
from glyphsketch.realdata.samples import DrawingSample, SampleSet
from glyphsketch.strokes import Drawing

A, ALPHA, B, C = 0x41, 0x391, 0x42, 0x43


def _samples(labels: list[int], datasets: list[str] | None = None) -> SampleSet:
    datasets = datasets or ["toy"] * len(labels)
    return SampleSet.from_samples(
        DrawingSample(dataset, str(index), "w", chr(label), label, [np.zeros((1, 2))])
        for index, (label, dataset) in enumerate(zip(labels, datasets, strict=True))
    )


def test_confusable_aware_scoring_accepts_any_group_member() -> None:
    predictions = np.array([[ALPHA, B, C, 0, 0], [C, B, A, 0, 0], [B, C, 0, 0, 0]])
    labels = np.array([A, A, A])
    hits = score_predictions(predictions, labels, {A: A, ALPHA: A})
    assert hits.top1.tolist() == [False, False, False]
    assert hits.top1_confusable.tolist() == [True, False, False]
    assert hits.top5.tolist() == [False, True, False]
    assert hits.top5_confusable.tolist() == [True, True, False]


def test_prediction_arrays_need_five_columns() -> None:
    with pytest.raises(ValueError):
        score_predictions(np.zeros((1, 3)), np.array([A]), {})


def test_macro_accuracy_averages_characters() -> None:
    labels = np.array([A, A, A, B])
    predictions = np.array([[A, 0, 0, 0, 0]] * 3 + [[C, 0, 0, 0, 0]])
    hits = score_predictions(predictions, labels, {})
    mask = np.ones(4, dtype=bool)
    assert Metrics.of(hits, mask, labels).top1 == pytest.approx(0.75)
    assert Metrics.macro(hits, mask, labels).top1 == pytest.approx(0.5)


def test_report_breaks_results_down() -> None:
    samples = _samples([A, A, B, C], ["one", "one", "two", "two"])
    predictions = np.array([[A] + [0] * 4, [B] + [0] * 4, [B] + [0] * 4, [A] + [0] * 4])
    zero_shot = np.array([False, False, True, True])
    report = evaluate_predictions(
        "toy", predictions, samples, zero_shot, {A: "Latin", B: "Latin", C: "Other"}, {}
    )
    assert report.overall.top1 == pytest.approx(0.5)
    assert report.by_dataset["one"].top1 == pytest.approx(0.5)
    assert report.by_subset["zero-shot"].top1 == pytest.approx(0.5)
    assert report.by_block["Latin"].samples == 3
    markdown = report_markdown(report)
    assert "| Dataset: two | 2 | 2 | 50.0 |" in markdown
    assert report.to_json()["by_block"]["Other"]["top1"] == 0.0


class _AlwaysA:
    def rank(self, drawings: Sequence[Drawing], k: int) -> np.ndarray:
        return np.tile(np.array([A, B, C, 0, 0][:k]), (len(drawings), 1))


def test_evaluate_runs_a_recognizer_in_batches() -> None:
    samples = _samples([A, B, C])
    report = evaluate(
        _AlwaysA(), "always A", samples, np.zeros(3, dtype=bool), {}, {}, batch_size=2
    )
    assert report.overall.top1 == pytest.approx(1 / 3)
    assert report.overall.top5 == pytest.approx(1.0)
