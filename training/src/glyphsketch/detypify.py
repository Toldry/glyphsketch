"""Comparison with Detypify (M10), on the test drawings of the symbols it recognizes.

Detypify (https://github.com/QuarticCat/detypify, MIT) is a Typst symbol classifier: a
CNN over 411 fixed classes. The pinned npm package ships its ONNX model and the class
list. Its preprocessing (``drawStrokes`` in the package) fits the drawing into
204 px of a 224×224 canvas, rounds points to whole pixels and draws 8 px white lines on
black with the browser's anti-aliasing. Here the same geometry is drawn with our distance
field rasterizer (round caps instead of the canvas's butt caps), which is close but not
pixel-identical.

**Overlap warning.** Detypify is trained on Detexify data, and our test writers are
Detexify users too. Nothing says its training data excludes them, so its numbers on
Detexify drawings may be inflated.
"""

import json
import tarfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from glyphsketch.download import download_file
from glyphsketch.parallel import default_workers, single_threaded_pool
from glyphsketch.strokes import Drawing, rasterize_segments, segments_of, simplify_stroke

PACKAGE_URL = "https://registry.npmjs.org/detypify-service/-/detypify-service-0.3.0.tgz"
PACKAGE_SHA256 = "1b0dc641e501e966177e3f6fcf939b87060633b5ecafbb53b7861c63dfa69c30"
PACKAGE_FILE = "detypify-service-0.3.0.tgz"
MODEL_FILE = "model.onnx"
SYMBOLS_FILE = "infer.json"
CANVAS_SIZE = 224
MARGIN = 20
LINE_WIDTH = 8.0
# Drawing hundreds of raw pen points costs about 0.7 s per image; within a quarter pixel
# the image doesn't change visibly.
SIMPLIFY_TOLERANCE = 0.25


def download_detypify(output_dir: Path) -> None:
    archive = download_file(PACKAGE_URL, output_dir / PACKAGE_FILE, PACKAGE_SHA256)
    with tarfile.open(archive) as bundle:
        for name, target in (("package/train/model.onnx", MODEL_FILE),
                             ("package/train/infer.json", SYMBOLS_FILE)):  # fmt: skip
            member = bundle.extractfile(name)
            assert member is not None
            (output_dir / target).write_bytes(member.read())


def detypify_image(strokes: Drawing) -> np.ndarray:
    """(224, 224) float32 image, ink = 1, framed and rounded as Detypify's drawStrokes."""
    points = np.concatenate([np.asarray(stroke, dtype=np.float64) for stroke in strokes])
    minimum, maximum = points.min(axis=0), points.max(axis=0)
    width = float(max(maximum - minimum))
    scale = (CANVAS_SIZE - MARGIN) / width if width > 1e-6 else 1.0
    centre = (minimum + maximum) / 2
    fitted = [
        np.round((np.asarray(stroke, dtype=np.float64) - centre) * scale + CANVAS_SIZE / 2)
        for stroke in strokes
        if len(stroke) > 1  # a canvas path of one point draws nothing
    ]
    if not fitted:
        return np.zeros((CANVAS_SIZE, CANVAS_SIZE), dtype=np.float32)
    simplified = [simplify_stroke(stroke, SIMPLIFY_TOLERANCE) for stroke in fitted]
    return rasterize_segments(segments_of(simplified), CANVAS_SIZE, LINE_WIDTH)


@dataclass
class DetypifyRecognizer:
    session: object
    code_points: np.ndarray  # class index → code point

    @classmethod
    def load(cls, directory: Path) -> "DetypifyRecognizer":
        import onnxruntime

        symbols = json.loads((directory / SYMBOLS_FILE).read_text(encoding="utf-8"))
        code_points = np.array([ord(symbol["char"]) for symbol in symbols], dtype=np.int64)
        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = default_workers()
        session = onnxruntime.InferenceSession(
            str(directory / MODEL_FILE), options, providers=["CPUExecutionProvider"]
        )
        return cls(session, code_points)

    def rank(self, drawings: Sequence[Drawing], k: int) -> np.ndarray:
        """Rasterize in worker processes, then run the model one image per call (its batch
        dimension is fixed at 1)."""
        workers = default_workers(len(drawings))
        with single_threaded_pool(workers) as pool:
            images = pool.map(detypify_image, drawings, chunksize=64)
        session = self.session
        input_name = session.get_inputs()[0].name  # type: ignore[attr-defined]
        rankings = np.zeros((len(drawings), k), dtype=np.int64)
        for row, image in enumerate(images):
            (scores,) = session.run(None, {input_name: image[None, None]})  # type: ignore[attr-defined]
            rankings[row] = self.code_points[np.argsort(-scores[0])[:k]]
        return rankings


COMPARISON_FILE = "comparison.json"
# Detypify takes about 0.17 s per drawing on the laptop, so a fixed random sample of the
# eligible test drawings is compared (standard error about 0.6 points at 6,000).
COMPARISON_SAMPLES = 6000
COMPARISON_SEED = 5


def compare(detypify_dir: Path) -> dict[str, object]:
    """Test-set comparison on the symbols Detypify knows; returns the reports as JSON."""
    import torch

    from glyphsketch.charset import CHARSET_FILE_NAME, load_charset
    from glyphsketch.eval_report import TestSet
    from glyphsketch.evaluation import TOP_K, evaluate_predictions
    from glyphsketch.export.build import (
        CHARSET_FILE,
        INDEX_FILE,
        ranker_from_metadata,
    )
    from glyphsketch.export.build import (
        MODEL_FILE as EXPORTED_MODEL_FILE,
    )
    from glyphsketch.export.formats import read_index, read_model
    from glyphsketch.export.ops import OperationsModule
    from glyphsketch.model.experiments import INDEX_DATA_STAGE, TEST_IMAGES
    from glyphsketch.model.ranking_eval import similarities
    from glyphsketch.model.train import embed_uint8_images
    from glyphsketch.paths import stage_dir
    from glyphsketch.ranking import keyboard_scripts_for

    test_set = TestSet.load(stage_dir("realdata"), stage_dir("charset"), stage_dir("confusables"))
    detypify = DetypifyRecognizer.load(detypify_dir)
    known = set(detypify.code_points.tolist())
    labels = test_set.samples.code_points.astype(np.int64)
    eligible = np.flatnonzero(np.isin(labels, list(known)))
    rng = np.random.default_rng(COMPARISON_SEED)
    size = min(COMPARISON_SAMPLES, len(eligible))
    rows = np.sort(rng.choice(eligible, size=size, replace=False))
    samples = test_set.samples.subset(rows)
    zero_shot = test_set.zero_shot[rows]
    characters = load_charset(stage_dir("charset") / CHARSET_FILE_NAME)
    block_of = {record.code_point: record.block for record in characters}
    script_of = {record.code_point: record.script for record in characters}

    export_dir = stage_dir("export")
    operations, _ = read_model((export_dir / EXPORTED_MODEL_FILE).read_bytes())
    index = read_index((export_dir / INDEX_FILE).read_bytes())
    metadata = json.loads((export_dir / CHARSET_FILE).read_text(encoding="utf-8"))
    ranker = ranker_from_metadata(metadata, index)
    images = np.load(stage_dir(INDEX_DATA_STAGE) / TEST_IMAGES, mmap_mode="r")[rows]
    module = OperationsModule(operations).eval()
    scores = similarities(index, embed_uint8_images(module, images, torch.device("cpu")))  # type: ignore[arg-type]
    restricted = np.where(np.isin(index.code_points, list(known))[None, :], scores, -np.inf)
    scripts = [keyboard_scripts_for(int(label), script_of) for label in samples.code_points]

    drawings = [samples.strokes(row) for row in range(len(samples))]
    everything = f"{len(index.code_points):,} characters"
    predictions = {
        "detypify": ("Detypify 0.3.0 (411 symbols)", detypify.rank(drawings, TOP_K)),
        "glyphsketch": (
            f"glyphsketch, ranked over all {everything}",
            ranker.top_characters(scores, TOP_K),
        ),
        "glyphsketch-restricted": (
            "glyphsketch, ranked over Detypify's 411 symbols",
            ranker.top_characters(restricted.astype(np.float32), TOP_K),
        ),
        "glyphsketch-tiles": (
            f"glyphsketch tiles, all {everything}",
            ranker.tile_representatives(scores, TOP_K, scripts),
        ),
    }
    reports = {}
    for key, (name, predicted) in predictions.items():
        report = evaluate_predictions(
            name, predicted, samples, zero_shot, block_of, test_set.group_of
        )
        reports[key] = report.to_json()
        print(f"  {name}: top-1 {report.overall.top1:.3f}, top-5 {report.overall.top5:.3f}, "
              f"top-5 (conf.) {report.overall.top5_confusable:.3f}", flush=True)  # fmt: skip
    return {
        "package": PACKAGE_URL,
        "symbols": len(known),
        "index_characters": len(index.code_points),
        "eligible_samples": len(eligible),
        "test_samples": len(rows),
        "test_characters": len(set(samples.code_points.tolist())),
        "reports": reports,
    }
