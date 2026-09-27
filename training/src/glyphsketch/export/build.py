"""The ``export`` stage: package a trained encoder for the inference engines (M8).

Outputs (in the stage directory, copied to the repository's ``export/``):

* ``glyphsketch-model.bin``: the encoder, batch norm and the PCA projection folded in,
  weights int8 per output channel;
* ``glyphsketch-index.bin``: the glyph index, int8 per vector;
* ``glyphsketch-charset.json``: per character its name, block, script, confusable group
  and log prior, plus the ranking settings, keyboard scripts and attributions;
* ``glyphsketch.onnx``: the same network as ONNX, a reference for benchmarking;
* ``fixtures.json``: parity fixtures, strokes → input image → embedding → ranking → tiles;
* ``README.md``: sizes, checksums and the numbers this package scores.

The PCA projection is fitted on the index vectors. Its size is the smallest candidate
whose accuracy on validation drawings (``ranking_eval.validation_set``) stays within
``max_validation_drop`` of the full embedding; the test set is not used for it.
"""

import base64
import hashlib
import json
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch

from glyphsketch.charset import CHARSET_FILE_NAME, CharacterRecord, format_code_point, load_charset
from glyphsketch.eval_report import TestSet
from glyphsketch.evaluation import TOP_K, evaluate_predictions, score_predictions
from glyphsketch.export.formats import index_bytes, model_bytes, read_index, read_model
from glyphsketch.export.ops import OperationsModule, fold_encoder, multiply_adds, run_numpy
from glyphsketch.model.experiments import (
    IMAGE_SIZE,
    TEST_IMAGES,
    index_options,
    synthetic_generator,
)
from glyphsketch.model.index import GlyphIndex
from glyphsketch.model.ranking_eval import (
    ranked_predictions,
    save_report,
    similarities,
    validation_set,
)
from glyphsketch.model.train import CHECKPOINT_FILE, embed_uint8_images, load_encoder
from glyphsketch.parallel import default_workers
from glyphsketch.paths import RESOURCES_DIR, data_dir, stage_dir
from glyphsketch.prior.build import PRIOR_FILE, FrequencyPrior
from glyphsketch.ranking import (
    Ranker,
    keyboard_scripts_for,
    on_every_keyboard,
    typed_on_every_keyboard,
)
from glyphsketch.strokes import CONTENT_FRACTION, DEFAULT_PEN_WIDTH_FRACTION, rasterize
from glyphsketch.ucd.files import UNICODE_VERSION

CONFIG_PATH = RESOURCES_DIR / "export.toml"
MODEL_FILE = "glyphsketch-model.bin"
INDEX_FILE = "glyphsketch-index.bin"
CHARSET_FILE = "glyphsketch-charset.json"
ONNX_FILE = "glyphsketch.onnx"
FIXTURES_FILE = "fixtures.json"
README_FILE = "README.md"
SIZE_BUDGET_BYTES = 10_000_000
SIMPLIFY_TOLERANCE = 0.25
FIXTURE_SAMPLE = 5
FIXTURE_TOP = 10
FIXTURE_COORDINATE_SCALE = 200.0
ATTRIBUTIONS = [
    "Glyph index computed from renders of free fonts listed in THIRD_PARTY.md.",
    "Character frequencies derived from Wikipedia (CC BY-SA 4.0 and GFDL), "
    "https://dumps.wikimedia.org.",
    "Contains information from the Detexify database (https://github.com/kirel/detexify-data), "
    "which is made available under the Open Database License (ODbL) v1.0.",
    "Character data from the Unicode Character Database (Unicode License V3).",
]


@dataclass(frozen=True)
class ExportConfig:
    run: str
    index: str
    prior_weight: float
    dims: int | None
    dims_candidates: tuple[int, ...]
    max_validation_drop: float
    fixture_characters: str


def load_export_config(path: Path = CONFIG_PATH) -> ExportConfig:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    return ExportConfig(
        run=raw["run"],
        index=raw["index"],
        prior_weight=float(raw["prior_weight"]),
        dims=None if raw["dims"] == "auto" else int(raw["dims"]),
        dims_candidates=tuple(raw["dims_candidates"]),
        max_validation_drop=float(raw["max_validation_drop"]),
        fixture_characters=raw["fixture_characters"],
    )


def checkpoint_path(config: ExportConfig) -> Path:
    return data_dir() / "experiments" / config.run / CHECKPOINT_FILE


def pca_basis(vectors: np.ndarray) -> np.ndarray:
    """(D, D) principal directions of the index vectors, columns by decreasing variance."""
    centred = vectors - vectors.mean(axis=0)
    _, _, directions = np.linalg.svd(centred, full_matrices=False)
    basis: np.ndarray = directions.T.astype(np.float32)
    return basis


def project(vectors: np.ndarray, projection: np.ndarray) -> np.ndarray:
    projected = vectors @ projection
    normalized: np.ndarray = projected / np.maximum(
        np.linalg.norm(projected, axis=1, keepdims=True), 1e-12
    )
    return normalized.astype(np.float32)


def projected_index(index: GlyphIndex, projection: np.ndarray) -> GlyphIndex:
    return GlyphIndex(project(index.vectors, projection), index.code_points, index.starts)


def validation_accuracy(
    index: GlyphIndex, queries: np.ndarray, labels: np.ndarray, ranker_arguments: dict[str, Any]
) -> tuple[float, float]:
    ranker = Ranker(index.code_points, **ranker_arguments)
    hits = score_predictions(
        ranked_predictions(ranker, similarities(index, queries)),
        labels,
        ranker_arguments["group_of"],
    )
    return float(hits.top1_confusable.mean()), float(hits.top5_confusable.mean())


def choose_dims(
    config: ExportConfig,
    index: GlyphIndex,
    queries: np.ndarray,
    labels: np.ndarray,
    ranker_arguments: dict[str, Any],
) -> tuple[int, list[dict[str, float]]]:
    """Smallest candidate within ``max_validation_drop`` of the full embedding on both
    confusable-aware top-1 and top-5."""
    basis = pca_basis(index.vectors)
    full = validation_accuracy(index, queries, labels, ranker_arguments)
    curve = [
        {"dims": index.vectors.shape[1], "top1_confusable": full[0], "top5_confusable": full[1]}
    ]
    chosen = index.vectors.shape[1]
    for dims in sorted(config.dims_candidates):
        projection = basis[:, :dims]
        accuracy = validation_accuracy(
            projected_index(index, projection), project(queries, projection), labels,
            ranker_arguments,
        )  # fmt: skip
        curve.append({"dims": dims, "top1_confusable": accuracy[0], "top5_confusable": accuracy[1]})
        print(f"  {dims} dims: top-1 (conf.) {accuracy[0]:.4f}, top-5 (conf.) {accuracy[1]:.4f} "
              f"(full: {full[0]:.4f}, {full[1]:.4f})", flush=True)  # fmt: skip
        within = all(full[k] - accuracy[k] <= config.max_validation_drop for k in range(2))
        if within and dims < chosen:
            chosen = dims
            break
    return chosen, curve


def charset_metadata(
    characters: Sequence[CharacterRecord],
    index: GlyphIndex,
    prior: FrequencyPrior,
    group_of: dict[int, int],
    config: ExportConfig,
    dims: int,
) -> dict[str, Any]:
    by_code_point = {record.code_point: record for record in characters}
    rows = []
    for code_point in index.code_points.tolist():
        record = by_code_point[code_point]
        rows.append(
            [
                code_point,
                record.name,
                record.block,
                record.script,
                record.general_category,
                group_of.get(code_point, code_point),
                round(prior.log_prior[code_point], 4),
            ]
        )
    return {
        "format": 1,
        "unicode_version": UNICODE_VERSION,
        "input_size": IMAGE_SIZE,
        "embedding_dim": dims,
        "rasterization": {
            "content_fraction": CONTENT_FRACTION,
            "pen_width_fraction": DEFAULT_PEN_WIDTH_FRACTION,
            "simplify_tolerance_pixels": SIMPLIFY_TOLERANCE,
        },
        "ranking": {
            "prior_weight": config.prior_weight,
            "prior_source": f"Wikipedia dumps of {prior.dump_date} (DECISIONS.md, D25)",
        },
        "keyboard_scripts": {language.code: list(language.scripts) for language in prior.languages},
        "columns": [
            "code_point",
            "name",
            "block",
            "script",
            "general_category",
            "group",
            "log_prior",
        ],
        "characters": rows,
        "attribution": ATTRIBUTIONS,
    }


def ranker_from_metadata(metadata: dict[str, Any], index: GlyphIndex) -> Ranker:
    """The ranker exactly as an engine builds it from the exported files."""
    column = {name: position for position, name in enumerate(metadata["columns"])}
    rows = metadata["characters"]

    def values(name: str) -> dict[int, Any]:
        return {row[column["code_point"]]: row[column[name]] for row in rows}

    scripts, categories = values("script"), values("general_category")
    return Ranker(
        index.code_points,
        values("log_prior"),
        metadata["ranking"]["prior_weight"],
        values("group"),
        scripts,
        frozenset(cp for cp in scripts if on_every_keyboard(scripts[cp], categories[cp])),
    )


def fixture_strokes(config: ExportConfig) -> list[tuple[int, list[list[list[float]]]]]:
    """Synthetic drawings (from fonts only), scaled to screen-like units and rounded."""
    generator = synthetic_generator()
    drawings = []
    for char in config.fixture_characters:
        strokes = generator.drawing(ord(char), FIXTURE_SAMPLE).strokes
        rounded = [
            np.round((np.asarray(stroke) + 0.5) * FIXTURE_COORDINATE_SCALE, 2).tolist()
            for stroke in strokes
        ]
        drawings.append((ord(char), rounded))
    return drawings


def build_fixtures(
    config: ExportConfig, model_data: bytes, index: GlyphIndex, metadata: dict[str, Any]
) -> dict[str, Any]:
    operations, input_size = read_model(model_data)
    ranker = ranker_from_metadata(metadata, index)
    cases = []
    for code_point, strokes in fixture_strokes(config):
        image = rasterize([np.array(stroke) for stroke in strokes], input_size,
                          simplify_tolerance=SIMPLIFY_TOLERANCE)  # fmt: skip
        embedding = run_numpy(operations, image.astype(np.float32) / 255.0)
        scores = index.scores(embedding[None, :])
        ranked = ranker.scores(scores)[0]
        top = np.argsort(-ranked, kind="stable")[:FIXTURE_TOP]
        tiles = {
            script: [
                {"representative": tile.representative, "members": list(tile.members),
                 "score": round(tile.score, 6)}
                for tile in ranker.tiles(scores[0], TOP_K, (script,))
            ]
            for script in ("Latin", "Greek")
        }  # fmt: skip
        cases.append(
            {
                "label": format_code_point(code_point),
                "strokes": strokes,
                "image_uint8_base64": base64.b64encode(image.tobytes()).decode("ascii"),
                "embedding": [round(float(value), 6) for value in embedding],
                "top_characters": [int(index.code_points[column]) for column in top],
                "top_scores": [round(float(ranked[column]), 6) for column in top],
                "tiles": tiles,
            }
        )
    return {
        "format": 1,
        "description": "Strokes in screen units (x right, y down). Rasterize with the "
        "default pen, run the model, score against the index, rank and tile. Expected "
        "tolerances: image ±1 per pixel, embedding and scores ±1e-4; ties within 1e-4 "
        "may swap places.",
        "cases": cases,
    }


def export_onnx(model_data: bytes, path: Path) -> float:
    """Write the ONNX reference; return its max deviation from the torch run of the file."""
    import onnxruntime

    operations, input_size = read_model(model_data)
    module = OperationsModule(operations).eval()
    example = torch.rand(2, 1, input_size, input_size)
    torch.onnx.export(
        module, (example,), str(path), input_names=["image"], output_names=["embedding"],
        dynamic_axes={"image": {0: "batch"}, "embedding": {0: "batch"}}, dynamo=False,
        opset_version=17,
    )  # fmt: skip
    session = onnxruntime.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    images = (torch.rand(8, 1, input_size, input_size) > 0.8).float()
    (onnx_output,) = session.run(None, {"image": images.numpy()})
    with torch.no_grad():
        expected = module(images).numpy()
    return float(np.abs(onnx_output - expected).max())


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_export(output_dir: Path) -> dict[str, Any]:
    config = load_export_config()
    torch.set_num_threads(default_workers())
    device = torch.device("cpu")
    model = load_encoder(checkpoint_path(config), device)
    _, index = index_options(model, device, only=config.index)[config.index]
    prior = FrequencyPrior.load(stage_dir("wikiprior") / PRIOR_FILE)
    characters = load_charset(stage_dir("charset") / CHARSET_FILE_NAME)
    test_set = TestSet.load(stage_dir("realdata"), stage_dir("charset"), stage_dir("confusables"))
    group_of = test_set.group_of
    script_of = {record.code_point: record.script for record in characters}
    ranker_arguments = {
        "log_prior": prior.log_prior,
        "weight": config.prior_weight,
        "group_of": group_of,
        "script_of": script_of,
        "typed_everywhere": typed_on_every_keyboard(characters),
    }

    curve: list[dict[str, float]] = []
    if config.dims is None:
        validation, images = validation_set()
        queries = embed_uint8_images(model, images, device)
        labels = validation.code_points.astype(np.int64)
        dims, curve = choose_dims(config, index, queries, labels, ranker_arguments)
    else:
        dims = config.dims
    full_dims = index.vectors.shape[1]
    projection = pca_basis(index.vectors)[:, :dims] if dims < full_dims else None
    print(f"  embedding: {dims} dims", flush=True)

    operations = fold_encoder(model, projection)
    model_data = model_bytes(operations, IMAGE_SIZE)
    export_index = projected_index(index, projection) if projection is not None else index
    index_data = index_bytes(export_index)
    stored_index = read_index(index_data)
    metadata = charset_metadata(characters, stored_index, prior, group_of, config, dims)
    charset_data = (json.dumps(metadata, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    fixtures = build_fixtures(config, model_data, stored_index, metadata)
    fixtures_data = (json.dumps(fixtures, ensure_ascii=False, indent=1) + "\n").encode()
    files = {
        MODEL_FILE: model_data,
        INDEX_FILE: index_data,
        CHARSET_FILE: charset_data,
        FIXTURES_FILE: fixtures_data,
    }
    for name, data in files.items():
        (output_dir / name).write_bytes(data)
    onnx_deviation = export_onnx(model_data, output_dir / ONNX_FILE)
    files[ONNX_FILE] = (output_dir / ONNX_FILE).read_bytes()

    evaluation = evaluate_package(config, model_data, stored_index, metadata, test_set, characters)
    shipped = len(model_data) + len(index_data) + len(charset_data)
    summary = {
        "run": config.run,
        "index": config.index,
        "dims": dims,
        "dims_curve": curve,
        "multiply_adds": multiply_adds(read_model(model_data)[0], IMAGE_SIZE),
        "shipped_bytes": shipped,
        "onnx_max_deviation": onnx_deviation,
        "evaluation": evaluation,
        "files": {
            name: {"bytes": len(data), "sha256": sha256_hex(data)} for name, data in files.items()
        },
    }
    (output_dir / README_FILE).write_text(render_readme(summary), encoding="utf-8")
    (output_dir / "export_summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    if shipped > SIZE_BUDGET_BYTES:
        raise RuntimeError(f"Export is {shipped:,} bytes, over the {SIZE_BUDGET_BYTES:,} budget")
    return summary


def evaluate_package(
    config: ExportConfig,
    model_data: bytes,
    index: GlyphIndex,
    metadata: dict[str, Any],
    test_set: TestSet,
    characters: Sequence[CharacterRecord],
) -> dict[str, Any]:
    """Test-set accuracy of the files as written (int8 weights and index)."""
    operations, _ = read_model(model_data)
    module = OperationsModule(operations).eval()
    images = np.load(stage_dir("encoderdata") / TEST_IMAGES)
    embeddings = embed_uint8_images(module, images, torch.device("cpu"))  # type: ignore[arg-type]
    scores = similarities(index, embeddings)
    ranker = ranker_from_metadata(metadata, index)
    script_of = {record.code_point: record.script for record in characters}
    block_of = {record.code_point: record.block for record in characters}
    labels = test_set.samples.code_points.astype(np.int64)
    scripts = [keyboard_scripts_for(int(label), script_of) for label in labels]
    results = {}
    for kind, predictions in (
        ("ranked", ranked_predictions(ranker, scores)),
        ("tiles", ranker.tile_representatives(scores, TOP_K, scripts)),
    ):
        name = f"Exported package ({config.run}, int8, {metadata['embedding_dim']} dims), " + (
            "ranked characters" if kind == "ranked" else "tiles"
        )
        report = evaluate_predictions(
            name, predictions, test_set.samples, test_set.zero_shot, block_of, test_set.group_of
        )
        report.notes.append(
            "The shipped files, read back: int8 weights and index, PCA projection, "
            f"prior weight {config.prior_weight}."
        )
        save_report(report.to_json(), f"export-{kind}")
        results[kind] = report.to_json()["overall"]
        print(f"  exported, {kind}: top-1 {report.overall.top1:.3f}, "
              f"top-5 (conf.) {report.overall.top5_confusable:.3f}", flush=True)  # fmt: skip
    return results


def render_readme(summary: dict[str, Any]) -> str:
    ranked, tiles = summary["evaluation"]["ranked"], summary["evaluation"]["tiles"]
    lines = [
        "# Exported model, index and metadata",
        "",
        "Generated by the `export` pipeline stage; do not edit. The formats are specified in",
        "`docs/export_format.md`, and the decisions behind them in DECISIONS.md (D27).",
        "",
        f"- Encoder: `{summary['run']}` run, index option `{summary['index']}`, "
        f"{summary['dims']}-dimensional embedding, {summary['multiply_adds'] / 1e6:.1f}M "
        "multiply-adds per drawing.",
        f"- Shipped size (model + index + metadata): {summary['shipped_bytes'] / 1e6:.2f} MB "
        f"of the {SIZE_BUDGET_BYTES / 1e6:.0f} MB budget.",
        f"- Test set, ranked characters: top-1 {100 * ranked['top1']:.1f}%, top-5 "
        f"{100 * ranked['top5']:.1f}%, top-5 confusable-aware "
        f"{100 * ranked['top5_confusable']:.1f}%.",
        f"- Test set, tiles: top-5 confusable-aware {100 * tiles['top5_confusable']:.1f}%.",
        "- ONNX reference: max deviation from the int8 file's network "
        f"{summary['onnx_max_deviation']:.1e}.",
        f"- Generated {datetime.now(UTC).date().isoformat()}.",
        "",
        "| File | Bytes | SHA-256 |",
        "|------|------:|---------|",
    ]
    for name, info in summary["files"].items():
        lines.append(f"| `{name}` | {info['bytes']:,} | `{info['sha256']}` |")
    lines += ["", "Attribution:", ""] + [f"- {line}" for line in ATTRIBUTIONS]
    return "\n".join(lines) + "\n"
