"""How well the exported package recognizes the characters added in D34 and D37 (synthetic
check).

No real handwriting exists for them, so this uses synthetic drawings from a generator seed
that neither training (seed 1) nor index option (b) uses, run through the exported files
exactly as the engines do. It is a proxy: synthetic drawings are closer to their fonts
than people's drawings are. Results are reported per kind of character; the user's
labelled drawings from the web demo are the real check.

Usage: ``uv run python -m glyphsketch.tools.new_characters [--run-name NAME]``
"""

import argparse
import json
from collections import defaultdict
from collections.abc import Sequence

import numpy as np
import torch

from glyphsketch.charset import CHARSET_FILE_NAME, load_charset
from glyphsketch.confusables import GROUPS_FILE, ConfusableGroups
from glyphsketch.eval_report import evaluations_dir
from glyphsketch.evaluation import TOP_K, score_predictions
from glyphsketch.export.build import CHARSET_FILE, INDEX_FILE, MODEL_FILE, ranker_from_metadata
from glyphsketch.export.formats import read_index, read_model
from glyphsketch.export.ops import OperationsModule
from glyphsketch.model.experiments import synthetic_generator
from glyphsketch.model.ranking_eval import similarities
from glyphsketch.model.train import embed_uint8_images
from glyphsketch.paths import stage_dir
from glyphsketch.synth.generator import generate_images

CHECK_SEED = 424242
SAMPLES_PER_CHARACTER = 5
# The groups and blocks D34, D37 and D40 added, and combining marks from any block.
KINDS = {
    "Emoji and pictographs": {"Emoji and pictographs"},
    "Egyptian hieroglyphs": {"Egyptian hieroglyphs"},
    "Living scripts (D40)": {"Living scripts", "Cham"},
    "Historic scripts (D40)": {"Historic scripts"},
    "Notations and numerals (D40)": {"Notations and numerals"},
    "Large historic sets (D40)": {"Large historic sets"},
    "Compatibility forms": {"Compatibility forms"},
    "Combining marks": {"Combining marks"},
}
BLOCK_KINDS = {
    "Box, block and braille": {
        "Box Drawing", "Block Elements", "Braille Patterns", "Symbols for Legacy Computing",
        "Symbols for Legacy Computing Supplement",
    },
    "Music and games": {
        "Musical Symbols", "Musical Symbols Supplement", "Chess Symbols", "Mahjong Tiles",
        "Domino Tiles", "Playing Cards",
    },
    "Other new symbols": {
        "Alchemical Symbols", "Ancient Symbols", "Geometric Shapes Extended",
        "Supplemental Arrows-C", "Ornamental Dingbats", "Enclosed Alphanumeric Supplement",
        "Miscellaneous Symbols Supplement", "Miscellaneous Symbols and Arrows Extended",
    },
}  # fmt: skip


def kind_of(group: str, block: str, general_category: str) -> str | None:
    if general_category in ("Mn", "Me"):
        return "Combining marks"
    for kind, groups in KINDS.items():
        if group in groups:
            return kind
    for kind, blocks in BLOCK_KINDS.items():
        if block in blocks:
            return kind
    return None


def run(run_name: str) -> dict[str, dict[str, float]]:
    export_dir = stage_dir("export")
    operations, _ = read_model((export_dir / MODEL_FILE).read_bytes())
    index = read_index((export_dir / INDEX_FILE).read_bytes())
    metadata = json.loads((export_dir / CHARSET_FILE).read_text(encoding="utf-8"))
    ranker = ranker_from_metadata(metadata, index)
    records = {r.code_point: r for r in load_charset(stage_dir("charset") / CHARSET_FILE_NAME)}
    group_of = ConfusableGroups.load(stage_dir("confusables") / GROUPS_FILE).group_of()

    kinds = {}
    for code_point in index.code_points.tolist():
        record = records[code_point]
        kind = kind_of(record.group, record.block, record.general_category)
        if kind is not None:
            kinds[code_point] = kind
    generator = synthetic_generator(seed=CHECK_SEED)
    available = set(generator.code_points)
    requests = [
        (code_point, sample)
        for code_point in sorted(kinds)
        if code_point in available
        for sample in range(SAMPLES_PER_CHARACTER)
    ]
    images = generate_images(generator, requests)
    labels = np.array([code_point for code_point, _ in requests], dtype=np.int64)
    module = OperationsModule(operations).eval()
    embeddings = embed_uint8_images(module, images, torch.device("cpu"))  # type: ignore[arg-type]
    # In chunks: all drawings against all characters at once would take many gigabytes.
    chunk = 1024
    tiles = np.concatenate(
        [
            ranker.tile_representatives(scores, TOP_K, [("Latin",)] * len(scores))
            for start in range(0, len(embeddings), chunk)
            for scores in [similarities(index, embeddings[start : start + chunk])]
        ]
    )
    hits = score_predictions(tiles, labels, group_of)
    rows: dict[str, list[int]] = defaultdict(list)
    for row, label in enumerate(labels.tolist()):
        rows[kinds[label]].append(row)
    results = {}
    for kind in [*KINDS, *BLOCK_KINDS]:
        selected = np.array(rows[kind], dtype=np.int64)
        if len(selected) == 0:
            continue
        results[kind] = {
            "characters": len(set(labels[selected].tolist())),
            "drawings": len(selected),
            "tile_top1": float(hits.top1[selected].mean()),
            "tile_top5_confusable": float(hits.top5_confusable[selected].mean()),
        }
        print(f"  {kind:24s} {results[kind]['characters']:5d} characters  "
              f"tile top-1 {results[kind]['tile_top1']:.3f}  "
              f"top-5 (conf.) {results[kind]['tile_top5_confusable']:.3f}", flush=True)  # fmt: skip
    payload = {"run": run_name, "seed": CHECK_SEED, "samples": SAMPLES_PER_CHARACTER,
               "kinds": results}  # fmt: skip
    (evaluations_dir().parent / "new-characters").mkdir(exist_ok=True)
    path = evaluations_dir().parent / "new-characters" / f"{run_name}.json"
    path.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    return results


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-name", default="export")
    args = parser.parse_args(argv)
    run(args.run_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
