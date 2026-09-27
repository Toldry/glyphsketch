"""M6 experiments: train encoders and evaluate every index option on the real test set.

``encoderdata`` (a pipeline stage) prepares the image pools once: synthetic training
drawings, 64 px glyph renders, and rasterized real drawings (training and test). Each
experiment trains one encoder into ``$DATA_DIR/experiments/<name>/`` and saves an
evaluation report per index option in ``$DATA_DIR/evaluations/``.

Usage: ``uv run python -m glyphsketch.model.experiments <name> [--budget-minutes M]``
"""

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
import torch

from glyphsketch.baselines import downsample_renders
from glyphsketch.confusables import GROUPS_FILE, ConfusableGroups
from glyphsketch.eval_report import TestSet, evaluations_dir
from glyphsketch.evaluation import TOP_K, evaluate_predictions
from glyphsketch.fonts import load_font_manifest
from glyphsketch.glyphs import GlyphTable, load_renders
from glyphsketch.model.data import CharacterPool, TrainingData, group_by_character, group_ids
from glyphsketch.model.encoder import GlyphEncoder
from glyphsketch.model.index import EmbeddingRecognizer, GlyphIndex, glyph_index, synthetic_index
from glyphsketch.model.train import CHECKPOINT_FILE, TrainingConfig, load_encoder, train_encoder
from glyphsketch.parallel import default_workers
from glyphsketch.paths import data_dir, stage_dir
from glyphsketch.realdata.build import SAMPLES_FILE
from glyphsketch.realdata.images import rasterize_samples
from glyphsketch.realdata.samples import SampleSet
from glyphsketch.realdata.splits import held_out_mask, training_mask
from glyphsketch.strokes import DEFAULT_PEN_WIDTH_FRACTION
from glyphsketch.synth.augment import AugmentationConfig
from glyphsketch.synth.generator import (
    GLYPH_STROKES_FILE,
    GlyphStrokeTable,
    SyntheticGenerator,
    generate_images,
)

IMAGE_SIZE = 64
TRAIN_SEED = 1
SYNTHETIC_PER_CHARACTER = 96
PROTOTYPE_SAMPLES = 16
REAL_PEN_SEED = 7

SYNTHETIC_IMAGES = "synthetic_images.npy"
SYNTHETIC_CODE_POINTS = "synthetic_code_points.npy"
GLYPH_IMAGES = "glyph_images.npy"
REAL_TRAIN_IMAGES = "real_train_images.npy"
REAL_TRAIN_CODE_POINTS = "real_train_code_points.npy"
TEST_IMAGES = "test_images.npy"


def synthetic_generator(seed: int = TRAIN_SEED) -> SyntheticGenerator:
    table = GlyphTable.load(stage_dir("glyphs"))
    strokes = GlyphStrokeTable.load(stage_dir("glyphstrokes") / GLYPH_STROKES_FILE)
    styles = {spec.id: spec.style for spec in load_font_manifest().fonts}
    return SyntheticGenerator(
        strokes, table, styles, AugmentationConfig(), image_size=IMAGE_SIZE, seed=seed
    )


def prepare_encoder_data(output_dir: Path, samples_per_character: int) -> dict[str, Any]:
    """Build and cache every image pool the experiments need."""
    generator = synthetic_generator()
    requests = [
        (code_point, sample)
        for code_point in generator.code_points
        for sample in range(samples_per_character)
    ]
    synthetic = generate_images(generator, requests)
    np.save(output_dir / SYNTHETIC_IMAGES, synthetic)
    np.save(
        output_dir / SYNTHETIC_CODE_POINTS,
        np.array([code_point for code_point, _ in requests], dtype=np.int32),
    )
    renders = load_renders(stage_dir("glyphs"), memory_map=False)
    glyphs = np.round(downsample_renders(renders, IMAGE_SIZE) * 255).astype(np.uint8)
    np.save(output_dir / GLYPH_IMAGES, glyphs)

    samples = SampleSet.load(stage_dir("realdata") / SAMPLES_FILE)
    train_rows = np.flatnonzero(training_mask(samples))
    train_samples = samples.subset(train_rows)
    config = AugmentationConfig()
    rng = np.random.default_rng(REAL_PEN_SEED)
    low, high = config.pen_width_fraction
    pens = np.exp(rng.uniform(np.log(low), np.log(high), size=len(train_samples))) * IMAGE_SIZE
    np.save(output_dir / REAL_TRAIN_IMAGES, rasterize_samples(train_samples, IMAGE_SIZE, pens))
    np.save(output_dir / REAL_TRAIN_CODE_POINTS, train_samples.code_points.astype(np.int32))

    test_samples = samples.subset(np.flatnonzero(held_out_mask(samples)))
    default_pen = DEFAULT_PEN_WIDTH_FRACTION * IMAGE_SIZE
    test_pens = np.full(len(test_samples), default_pen)
    np.save(output_dir / TEST_IMAGES, rasterize_samples(test_samples, IMAGE_SIZE, test_pens))
    return {
        "synthetic_images": len(synthetic),
        "glyph_images": len(glyphs),
        "real_train_images": len(train_samples),
        "test_images": len(test_samples),
    }


def load_training_data(use_real: bool, exclude: set[int] | None = None) -> TrainingData:
    encoder_data = stage_dir("encoderdata")
    table = GlyphTable.load(stage_dir("glyphs"))
    characters = np.array(sorted(set(table.code_points.tolist()) - (exclude or set())))
    groups = ConfusableGroups.load(stage_dir("confusables") / GROUPS_FILE)
    synthetic = group_by_character(
        np.load(encoder_data / SYNTHETIC_IMAGES, mmap_mode="r"),
        np.load(encoder_data / SYNTHETIC_CODE_POINTS),
        characters,
    )
    glyphs = group_by_character(np.load(encoder_data / GLYPH_IMAGES), table.code_points, characters)
    real: CharacterPool | None = None
    if use_real:
        real = group_by_character(
            np.load(encoder_data / REAL_TRAIN_IMAGES),
            np.load(encoder_data / REAL_TRAIN_CODE_POINTS),
            characters,
        )
    return TrainingData(
        characters=characters,
        groups=group_ids(characters, groups.group_of()),
        synthetic=synthetic,
        glyphs=glyphs,
        real=real,
    )


@dataclass(frozen=True)
class Experiment:
    name: str
    description: str
    training: TrainingConfig
    use_real: bool


EXPERIMENTS = {
    experiment.name: experiment
    for experiment in (
        Experiment(
            "synthetic-only",
            "trained on synthetic drawings only",
            TrainingConfig(real_probability=0.0),
            use_real=False,
        ),
        Experiment(
            "synthetic-and-real",
            "trained on synthetic drawings plus real training drawings",
            TrainingConfig(real_probability=0.35),
            use_real=True,
        ),
    )
}


def index_options(
    model: GlyphEncoder, device: torch.device, only: str | None = None
) -> dict[str, tuple[str, GlyphIndex]]:
    """Every index option (or just ``only``), with a description of each."""
    options: dict[str, tuple[str, GlyphIndex]] = {}
    if only in (None, "a-per-font", "a-mean"):
        table = GlyphTable.load(stage_dir("glyphs"))
        glyph_images = np.load(stage_dir("encoderdata") / GLYPH_IMAGES)
        per_font = glyph_index(model, glyph_images, table.code_points, device)
        options["a-per-font"] = ("index (a): glyph render per font, best match", per_font)
        options["a-mean"] = ("index (a): mean of the glyph renders", per_font.averaged())
    if only in (None, "b-synthetic"):
        generator = synthetic_generator()
        prototypes = synthetic_index(
            model, generator, generator.code_points, PROTOTYPE_SAMPLES, device
        )
        options["b-synthetic"] = (
            f"index (b): mean of {PROTOTYPE_SAMPLES} synthetic drawings",
            prototypes,
        )
    return options if only is None else {only: options[only]}


def evaluate_experiment(
    experiment: Experiment, model: GlyphEncoder, device: torch.device, training: dict[str, Any]
) -> list[dict[str, Any]]:
    test_set = TestSet.load(stage_dir("realdata"), stage_dir("charset"), stage_dir("confusables"))
    test_images = np.load(stage_dir("encoderdata") / TEST_IMAGES)
    results = []
    for option, (option_description, index) in index_options(model, device).items():
        recognizer = EmbeddingRecognizer(model, index, device)
        predictions = recognizer.rank_images(test_images, TOP_K)
        name = f"Encoder ({experiment.name}), {option_description}"
        report = evaluate_predictions(
            name, predictions, test_set.samples, test_set.zero_shot, test_set.block_of,
            test_set.group_of,
        )  # fmt: skip
        report.notes.append(
            f"Encoder {experiment.description}; {training['steps_completed']} steps in "
            f"{training['seconds'] / 60:.0f} min; index vectors: {len(index.vectors)}."
        )
        slug = f"encoder-{experiment.name}-{option}"
        payload = report.to_json() | {"slug": slug}
        (evaluations_dir() / f"{slug}.json").write_text(
            json.dumps(payload, indent=1) + "\n", encoding="utf-8"
        )
        results.append(payload)
        print(
            f"  {option}: top-1 {report.overall.top1:.3f}  top-5 {report.overall.top5:.3f}  "
            f"top-5 (conf.) {report.overall.top5_confusable:.3f}  "
            f"zero-shot top-5 (conf.) {report.by_subset['zero-shot'].top5_confusable:.3f}"
        )
    return results


def run_experiment(
    name: str,
    budget_minutes: float | None = None,
    threads: int | None = None,
    steps: int | None = None,
    batch_characters: int | None = None,
    run_name: str | None = None,
) -> None:
    """Train and evaluate; ``run_name`` (default: ``name``) names the outputs and reports."""
    experiment = EXPERIMENTS[name]
    torch.set_num_threads(threads or default_workers())
    training_config = experiment.training
    if budget_minutes is not None:
        training_config = replace(training_config, time_budget_seconds=budget_minutes * 60)
    if steps is not None:
        training_config = replace(training_config, steps=steps)
    if batch_characters is not None:
        training_config = replace(training_config, batch_characters=batch_characters)
    experiment = replace(experiment, name=run_name or name, training=training_config)
    output_dir = data_dir() / "experiments" / experiment.name
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    data = load_training_data(experiment.use_real)
    print(f"[{experiment.name}] {len(data.characters)} characters, device {device}", flush=True)
    summary = train_encoder(data, training_config, output_dir, device)
    model = load_encoder(output_dir / CHECKPOINT_FILE, device).to(device)
    evaluate_experiment(experiment, model, device, summary)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("name", choices=sorted(EXPERIMENTS))
    parser.add_argument("--budget-minutes", type=float, default=None)
    parser.add_argument("--threads", type=int, default=None, help="default: half the cores")
    parser.add_argument("--steps", type=int, default=None, help="override the step count")
    parser.add_argument("--batch-characters", type=int, default=None)
    parser.add_argument("--run-name", default=None, help="names outputs; default: the name")
    args = parser.parse_args(argv)
    run_experiment(
        args.name,
        args.budget_minutes,
        args.threads,
        args.steps,
        args.batch_characters,
        args.run_name,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
