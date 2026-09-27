"""Tune the prior weight and evaluate ranking and tiles for a trained encoder (M7).

The weight is tuned on real drawings the encoder has not seen: a fixed subsample of the
training split (train-split writers, characters that are not zero-shot). Only encoders
trained without real drawings may be tuned that way; for the others, pass the weight
tuned on a synthetic-only encoder. The test set is never used for tuning.

For the index option given, it saves two reports next to the plain one:

* ``…-prior``: characters ranked by similarity + weight · log prior;
* ``…-tiles``: one tile per confusable group, shown by its representative for a keyboard
  in the drawn character's script (Latin for symbols), see ``ranking``.

Usage: ``uv run python -m glyphsketch.model.ranking_eval <run name> [--weight W]``
"""

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

import numpy as np
import torch

from glyphsketch.charset import CHARSET_FILE_NAME, load_charset
from glyphsketch.eval_report import TestSet, evaluations_dir
from glyphsketch.evaluation import TOP_K, evaluate_predictions, score_predictions
from glyphsketch.model.experiments import IMAGE_SIZE, TEST_IMAGES, index_options
from glyphsketch.model.index import GlyphIndex
from glyphsketch.model.train import CHECKPOINT_FILE, LOG_FILE, embed_uint8_images, load_encoder
from glyphsketch.parallel import default_workers
from glyphsketch.paths import data_dir, stage_dir
from glyphsketch.prior.build import PRIOR_FILE, FrequencyPrior
from glyphsketch.ranking import Ranker, keyboard_scripts_for, typed_on_every_keyboard
from glyphsketch.realdata.build import SAMPLES_FILE
from glyphsketch.realdata.images import rasterize_samples
from glyphsketch.realdata.samples import SampleSet
from glyphsketch.realdata.splits import training_mask
from glyphsketch.strokes import DEFAULT_PEN_WIDTH_FRACTION

VALIDATION_SAMPLES = 20_000
VALIDATION_SEED = 11
WEIGHT_GRID = (0.0, 0.001, 0.002, 0.003, 0.004, 0.005, 0.0075, 0.01, 0.02, 0.05)
BATCH = 1024


def validation_set() -> tuple[SampleSet, np.ndarray]:
    """A fixed subsample of the training split, rasterized like test input."""
    samples = SampleSet.load(stage_dir("realdata") / SAMPLES_FILE)
    rows = np.flatnonzero(training_mask(samples))
    rng = np.random.default_rng(VALIDATION_SEED)
    chosen = np.sort(rng.choice(rows, size=min(VALIDATION_SAMPLES, len(rows)), replace=False))
    subset = samples.subset(chosen)
    pens = np.full(len(subset), DEFAULT_PEN_WIDTH_FRACTION * IMAGE_SIZE)
    return subset, rasterize_samples(subset, IMAGE_SIZE, pens)


def similarities(index: GlyphIndex, embeddings: np.ndarray) -> np.ndarray:
    return np.concatenate(
        [
            index.scores(embeddings[start : start + BATCH])
            for start in range(0, len(embeddings), BATCH)
        ]
    )


def ranked_predictions(ranker: Ranker, scores: np.ndarray) -> np.ndarray:
    return np.concatenate(
        [
            ranker.top_characters(scores[start : start + BATCH], TOP_K)
            for start in range(0, len(scores), BATCH)
        ]
    )


def tune_weight(
    index: GlyphIndex,
    prior: FrequencyPrior,
    group_of: dict[int, int],
    script_of: dict[int, str],
    typed_everywhere: frozenset[int],
    scores: np.ndarray,
    labels: np.ndarray,
) -> tuple[float, list[dict[str, float]]]:
    """The grid weight with the best confusable-aware top-1 (then top-5) on validation."""
    curve = []
    for weight in WEIGHT_GRID:
        ranker = Ranker(
            index.code_points, prior.log_prior, weight, group_of, script_of, typed_everywhere
        )
        hits = score_predictions(ranked_predictions(ranker, scores), labels, group_of)
        curve.append(
            {
                "weight": weight,
                "top1": float(hits.top1.mean()),
                "top5": float(hits.top5.mean()),
                "top1_confusable": float(hits.top1_confusable.mean()),
                "top5_confusable": float(hits.top5_confusable.mean()),
            }
        )
        print(
            f"  weight {weight:.3f}: top-1 {curve[-1]['top1']:.3f}  "
            f"top-1 (conf.) {curve[-1]['top1_confusable']:.3f}  "
            f"top-5 (conf.) {curve[-1]['top5_confusable']:.3f}",
            flush=True,
        )
    best = max(curve, key=lambda point: (point["top1_confusable"], point["top5_confusable"]))
    return best["weight"], curve


def trained_on_real(run_name: str) -> bool:
    log = json.loads((data_dir() / "experiments" / run_name / LOG_FILE).read_text())
    return float(log["config"]["real_probability"]) > 0


def save_report(payload: dict[str, Any], slug: str) -> None:
    (evaluations_dir() / f"{slug}.json").write_text(
        json.dumps(payload | {"slug": slug}, indent=1) + "\n", encoding="utf-8"
    )


def run(run_name: str, option: str, weight: float | None) -> dict[str, Any]:
    if weight is None and trained_on_real(run_name):
        raise SystemExit(
            f"{run_name} was trained on real drawings, so the validation set isn't unseen: "
            "pass --weight (tuned on a synthetic-only encoder)."
        )
    torch.set_num_threads(default_workers())
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = load_encoder(data_dir() / "experiments" / run_name / CHECKPOINT_FILE, device)
    model = model.to(device)
    description, index = index_options(model, device, only=option)[option]
    prior = FrequencyPrior.load(stage_dir("wikiprior") / PRIOR_FILE)
    characters = load_charset(stage_dir("charset") / CHARSET_FILE_NAME)
    script_of = {record.code_point: record.script for record in characters}
    typed_everywhere = typed_on_every_keyboard(characters)
    block_of = {record.code_point: record.block for record in characters}
    test_set = TestSet.load(stage_dir("realdata"), stage_dir("charset"), stage_dir("confusables"))
    group_of = test_set.group_of

    curve: list[dict[str, float]] = []
    if weight is None:
        validation, validation_images = validation_set()
        validation_scores = similarities(
            index, embed_uint8_images(model, validation_images, device)
        )
        labels = validation.code_points.astype(np.int64)
        weight, curve = tune_weight(
            index, prior, group_of, script_of, typed_everywhere, validation_scores, labels
        )
        print(f"  chosen weight {weight}", flush=True)

    test_images = np.load(stage_dir("encoderdata") / TEST_IMAGES)
    test_scores = similarities(index, embed_uint8_images(model, test_images, device))
    ranker = Ranker(
        index.code_points, prior.log_prior, weight, group_of, script_of, typed_everywhere
    )
    labels = test_set.samples.code_points.astype(np.int64)
    scripts = [keyboard_scripts_for(int(label), script_of) for label in labels]
    results: dict[str, Any] = {"weight": weight, "curve": curve}
    prior_note = (
        f"Score = similarity + {weight} · log prior (Wikipedia dumps of {prior.dump_date}); "
        + ("weight tuned on 20,000 unseen training-split drawings." if curve else "weight given.")
    )
    for kind, predictions in (
        ("prior", ranked_predictions(ranker, test_scores)),
        ("tiles", ranker.tile_representatives(test_scores, TOP_K, scripts)),
    ):
        name = f"Encoder ({run_name}), {description}, " + (
            "with prior" if kind == "prior" else "tiles"
        )
        report = evaluate_predictions(
            name, predictions, test_set.samples, test_set.zero_shot, block_of, group_of
        )
        report.notes.append(prior_note)
        if kind == "tiles":
            report.notes.append(
                "One tile per confusable group; the tile shows the member in the keyboard's "
                "script, assumed to be the drawn character's (Latin for symbols). Exact "
                "top-1 therefore measures the representative choice."
            )
        save_report(
            report.to_json() | {"weight": weight, "curve": curve},
            f"encoder-{run_name}-{option}-{kind}",
        )
        results[kind] = report.to_json()["overall"]
        print(
            f"  {kind}: top-1 {report.overall.top1:.3f}  top-5 {report.overall.top5:.3f}  "
            f"top-1 (conf.) {report.overall.top1_confusable:.3f}  "
            f"top-5 (conf.) {report.overall.top5_confusable:.3f}",
            flush=True,
        )
    return results


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_name")
    parser.add_argument(
        "--index", default="a-per-font", choices=["a-per-font", "a-mean", "b-synthetic"]
    )
    parser.add_argument("--weight", type=float, default=None)
    args = parser.parse_args(argv)
    run(args.run_name, args.index, args.weight)
    return 0


if __name__ == "__main__":
    sys.exit(main())
