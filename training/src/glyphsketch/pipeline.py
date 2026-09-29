"""Run the training pipeline stage by stage, caching each stage's output in ``$DATA_DIR``.

Usage: ``python -m glyphsketch.pipeline {all|<stage> ...} [--force] [--list]``

Each stage writes its outputs to ``$DATA_DIR/<stage>/`` and, on success, a stamp file that
records the stage version and the run ids of the upstream stages it was built from. A stage
is up to date when its stamp matches its current version and its dependencies' latest runs,
so re-running an upstream stage (or bumping a stage's version after changing its logic)
invalidates everything downstream of it.
"""

import argparse
import hashlib
import json
import sys
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from glyphsketch.paths import REPO_ROOT, data_dir, stage_dir

if TYPE_CHECKING:
    from glyphsketch.eval_report import TestSet

STAMP_FILE_NAME = ".stage-complete.json"


@dataclass(frozen=True)
class StageContext:
    """What a running stage gets: its own output directory and access to upstream outputs."""

    output_dir: Path

    def input_dir(self, stage_name: str) -> Path:
        return stage_dir(stage_name)


@dataclass(frozen=True)
class Stage:
    name: str
    description: str
    run: Callable[[StageContext], None]
    depends_on: tuple[str, ...] = ()
    # Bump when a change to the stage's logic should invalidate its cached output.
    version: str = "1"


def _read_stamp(stage_name: str) -> dict[str, Any] | None:
    stamp_path = stage_dir(stage_name) / STAMP_FILE_NAME
    if not stamp_path.is_file():
        return None
    try:
        stamp: dict[str, Any] = json.loads(stamp_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return stamp


class Pipeline:
    def __init__(self, stages: Sequence[Stage]) -> None:
        self.stages: dict[str, Stage] = {}
        for stage in stages:
            if stage.name in self.stages:
                raise ValueError(f"Duplicate stage name: {stage.name}")
            unknown = [dep for dep in stage.depends_on if dep not in self.stages]
            if unknown:
                raise ValueError(
                    f"Stage {stage.name} depends on {unknown}, which must be registered first"
                )
            self.stages[stage.name] = stage

    def execution_order(self, targets: Sequence[str]) -> list[Stage]:
        """Return the targets and all their dependencies, in registration order."""
        needed: set[str] = set()
        pending = list(targets)
        while pending:
            name = pending.pop()
            if name not in self.stages:
                raise KeyError(f"Unknown stage: {name}")
            if name not in needed:
                needed.add(name)
                pending.extend(self.stages[name].depends_on)
        return [stage for name, stage in self.stages.items() if name in needed]

    def is_up_to_date(self, stage: Stage) -> bool:
        stamp = _read_stamp(stage.name)
        if stamp is None or stamp.get("version") != stage.version:
            return False
        return bool(stamp.get("inputs") == self._current_input_run_ids(stage))

    def _current_input_run_ids(self, stage: Stage) -> dict[str, str | None]:
        run_ids: dict[str, str | None] = {}
        for dependency in stage.depends_on:
            dependency_stamp = _read_stamp(dependency)
            run_ids[dependency] = dependency_stamp["run_id"] if dependency_stamp else None
        return run_ids

    def run(self, targets: Sequence[str], force: bool = False) -> list[str]:
        """Run the targets (and stale dependencies); return the names of stages that ran."""
        executed: list[str] = []
        for stage in self.execution_order(targets):
            forced = force and stage.name in targets
            if not forced and self.is_up_to_date(stage):
                print(f"[{stage.name}] up to date, skipping")
                continue
            print(f"[{stage.name}] {stage.description}")
            started = time.monotonic()
            output_dir = stage_dir(stage.name)
            (output_dir / STAMP_FILE_NAME).unlink(missing_ok=True)
            stage.run(StageContext(output_dir=output_dir))
            stamp = {
                "stage": stage.name,
                "version": stage.version,
                "run_id": uuid.uuid4().hex,
                "inputs": self._current_input_run_ids(stage),
                "completed_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "seconds": round(time.monotonic() - started, 1),
            }
            (output_dir / STAMP_FILE_NAME).write_text(
                json.dumps(stamp, indent=2) + "\n", encoding="utf-8"
            )
            print(f"[{stage.name}] done in {stamp['seconds']} s")
            executed.append(stage.name)
        return executed


def file_fingerprint(path: Path) -> str:
    """Short content hash, for stage versions that must change when an input file changes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def publish_report(report_path: Path, name: str) -> None:
    """Copy a small Markdown report into ``docs/reports/`` so it is versioned with the code."""
    destination = REPO_ROOT / "docs" / "reports" / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(report_path.read_text(encoding="utf-8"), encoding="utf-8")


def run_ucd_stage(context: StageContext) -> None:
    from glyphsketch.ucd.files import download_ucd

    download_ucd(context.output_dir)


def run_charset_stage(context: StageContext) -> None:
    from glyphsketch.charset import (
        CHARSET_FILE_NAME,
        build_charset,
        load_charset_config,
        write_charset,
    )
    from glyphsketch.ucd.parse import UnicodeDatabase

    build = build_charset(UnicodeDatabase(context.input_dir("ucd")), load_charset_config())
    write_charset(build, context.output_dir / CHARSET_FILE_NAME)
    print(f"  {len(build.characters)} characters; excluded: {dict(build.exclusion_counts)}")


def run_fonts_stage(context: StageContext) -> None:
    from glyphsketch.fonts import download_fonts, load_font_manifest

    download_fonts(context.output_dir, load_font_manifest())


def run_glyphs_stage(context: StageContext) -> None:
    from glyphsketch.charset import CHARSET_FILE_NAME, load_charset
    from glyphsketch.fonts import load_font_manifest
    from glyphsketch.glyphs import COVERAGE_REPORT_FILE, render_all_fonts, write_glyph_outputs

    characters = load_charset(context.input_dir("charset") / CHARSET_FILE_NAME)
    manifest = load_font_manifest()
    results = render_all_fonts(characters, manifest, context.input_dir("fonts"))
    summary = write_glyph_outputs(context.output_dir, characters, manifest, results)
    publish_report(context.output_dir / COVERAGE_REPORT_FILE, "glyph_coverage.md")
    print(
        f"  {len(summary['characters'])} characters covered, "
        f"{len(summary['dropped_characters'])} dropped, {summary['render_count']} renders"
    )


def run_detexify_stage(context: StageContext) -> None:
    from glyphsketch.realdata.detexify import download_detexify

    download_detexify(context.output_dir)


def run_omniglot_stage(context: StageContext) -> None:
    from glyphsketch.realdata.omniglot import download_omniglot

    download_omniglot(context.output_dir)


def run_uji_stage(context: StageContext) -> None:
    from glyphsketch.realdata.uji import download_uji

    download_uji(context.output_dir)


def run_realdata_stage(context: StageContext) -> None:
    from glyphsketch.charset import CHARSET_FILE_NAME, load_charset
    from glyphsketch.glyphs import GlyphTable
    from glyphsketch.realdata.build import (
        REPORT_FILE,
        SAMPLES_FILE,
        build_real_samples,
        real_data_report,
    )

    table = GlyphTable.load(context.input_dir("glyphs"))
    samples, counts = build_real_samples(
        set(table.code_points.tolist()),
        context.input_dir("detexify"),
        context.input_dir("omniglot"),
        context.input_dir("uji"),
    )
    samples.save(context.output_dir / SAMPLES_FILE)
    characters = {
        record.code_point: record
        for record in load_charset(context.input_dir("charset") / CHARSET_FILE_NAME)
    }
    report = real_data_report(samples, counts, characters)
    (context.output_dir / REPORT_FILE).write_text(report, encoding="utf-8")
    publish_report(context.output_dir / REPORT_FILE, "real_data.md")
    print(f"  {len(samples)} samples of {len(set(samples.code_points.tolist()))} characters")


def run_confusables_stage(context: StageContext) -> None:
    from glyphsketch.charset import CHARSET_FILE_NAME, load_charset, load_charset_config
    from glyphsketch.confusables import REPORT_FILE, build_confusable_groups, write_groups
    from glyphsketch.glyphs import GlyphTable, load_renders
    from glyphsketch.ucd.parse import UnicodeDatabase

    ucd = UnicodeDatabase(context.input_dir("ucd"))
    glyphs_dir = context.input_dir("glyphs")
    joining = {group.name for group in load_charset_config().groups if group.join_lookalikes}
    records = load_charset(context.input_dir("charset") / CHARSET_FILE_NAME)
    joiners = {record.code_point for record in records if record.group in joining}
    groups, pairs = build_confusable_groups(
        ucd, load_renders(glyphs_dir), GlyphTable.load(glyphs_dir), joiners=joiners
    )
    names = {code_point: entry.name for code_point, entry in ucd.entries.items()}
    write_groups(context.output_dir, groups, pairs, names)
    publish_report(context.output_dir / REPORT_FILE, "confusable_groups.md")
    print(f"  {len(groups.groups)} groups from {len(pairs)} candidate pairs")


def run_wikiprior_stage(context: StageContext) -> None:
    from glyphsketch.charset import CHARSET_FILE_NAME, load_charset
    from glyphsketch.glyphs import GlyphTable
    from glyphsketch.prior.build import PRIOR_FILE, REPORT_FILE, build_prior, render_report
    from glyphsketch.prior.sample import load_prior_config

    covered = set(GlyphTable.load(context.input_dir("glyphs")).code_points.tolist())
    characters = [
        record
        for record in load_charset(context.input_dir("charset") / CHARSET_FILE_NAME)
        if record.code_point in covered
    ]
    from glyphsketch.ucd import files as ucd_files
    from glyphsketch.ucd.parse import code_points_with_property

    pictographic = code_points_with_property(
        context.input_dir("ucd") / ucd_files.EMOJI_DATA.relative_path, "Extended_Pictographic"
    )
    config = load_prior_config()
    cache_dir = data_dir() / "wikipedia-samples" / config.dump_date
    prior = build_prior(config, characters, cache_dir, set(pictographic))
    (context.output_dir / PRIOR_FILE).write_text(
        json.dumps(prior, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    (context.output_dir / REPORT_FILE).write_text(
        render_report(prior, characters), encoding="utf-8"
    )
    publish_report(context.output_dir / REPORT_FILE, REPORT_FILE)
    for language in prior["languages"]:
        print(
            f"  {language['code']}: {language['pages']:,} articles, "
            f"{language['characters']:,} characters"
        )


def run_export_stage(context: StageContext) -> None:
    import shutil

    from glyphsketch.export.build import run_export

    summary = run_export(context.output_dir)
    destination = REPO_ROOT / "export"
    destination.mkdir(exist_ok=True)
    for name in [*summary["files"], "README.md"]:
        shutil.copyfile(context.output_dir / name, destination / name)
    print(f"  {summary['shipped_bytes'] / 1e6:.2f} MB shipped, copied to {destination}")


def export_version() -> str:
    """Changes with the export settings and with the encoder checkpoint they name."""
    from glyphsketch import ranking
    from glyphsketch.export import build, formats, ops

    checkpoint = build.checkpoint_path(build.load_export_config())
    encoder = file_fingerprint(checkpoint) if checkpoint.exists() else "no-checkpoint"
    code = "".join(
        file_fingerprint(Path(module.__file__ or ""))[:6]
        for module in (build, formats, ops, ranking)
    )
    return f"1-{file_fingerprint(build.CONFIG_PATH)}-{encoder}-{code}"


def run_detypify_stage(context: StageContext) -> None:
    from glyphsketch.detypify import COMPARISON_FILE, compare, download_detypify

    download_detypify(context.output_dir)
    result = compare(context.output_dir)
    (context.output_dir / COMPARISON_FILE).write_text(json.dumps(result, indent=1) + "\n")


def run_glyphstrokes_stage(context: StageContext) -> None:
    from glyphsketch.synth.generator import GLYPH_STROKES_FILE, extract_all_strokes

    table = extract_all_strokes(context.input_dir("glyphs"))
    table.save(context.output_dir / GLYPH_STROKES_FILE)
    counts = np.diff(table.render_offsets)
    print(
        f"  {len(table)} renders, {int((counts == 0).sum())} without strokes, "
        f"median {int(np.median(counts))} strokes per render"
    )


def run_indexdata_stage(context: StageContext) -> None:
    from glyphsketch.model.experiments import prepare_index_data

    counts = prepare_index_data(context.output_dir)
    print("  " + ", ".join(f"{name}: {count}" for name, count in counts.items()))


def run_encoderdata_stage(context: StageContext) -> None:
    from glyphsketch.model.experiments import SYNTHETIC_PER_CHARACTER, prepare_encoder_data

    counts = prepare_encoder_data(context.output_dir, SYNTHETIC_PER_CHARACTER)
    print("  " + ", ".join(f"{name}: {count}" for name, count in counts.items()))


def load_test_set(context: StageContext) -> "TestSet":
    from glyphsketch.eval_report import TestSet

    return TestSet.load(
        context.input_dir("realdata"),
        context.input_dir("charset"),
        context.input_dir("confusables"),
    )


def run_baselines_stage(context: StageContext) -> None:
    from glyphsketch.baselines import (
        HOG_IMAGE_SIZE,
        PIXEL_IMAGE_SIZE,
        QUERY_PEN_WIDTH_FRACTION,
        hog_recognizer,
        pixel_recognizer,
    )
    from glyphsketch.eval_report import run_and_save
    from glyphsketch.glyphs import GlyphTable, load_renders

    test_set = load_test_set(context)
    glyphs_dir = context.input_dir("glyphs")
    table = GlyphTable.load(glyphs_dir)
    renders = load_renders(glyphs_dir, memory_map=False)
    pen = f"drawings rasterized with a pen {QUERY_PEN_WIDTH_FRACTION:.0%} of the image wide"
    for slug, name, build, note in (
        (
            "pixels",
            "Baseline: nearest render, raw pixels",
            pixel_recognizer,
            f"Cosine similarity of blurred {PIXEL_IMAGE_SIZE}×{PIXEL_IMAGE_SIZE} images; {pen}.",
        ),
        (
            "hog",
            "Baseline: nearest render, HOG",
            hog_recognizer,
            f"Cosine similarity of HOG descriptors of {HOG_IMAGE_SIZE}×{HOG_IMAGE_SIZE} images "
            f"(9 orientations, 8 px cells, 2×2 blocks); {pen}.",
        ),
    ):
        report = run_and_save(build(renders, table), name, slug, test_set, [note])
        print(f"  {name}: top-1 {report.overall.top1:.3f}, top-5 {report.overall.top5:.3f}")


def run_evalreport_stage(context: StageContext) -> None:
    from glyphsketch.detypify import COMPARISON_FILE
    from glyphsketch.eval_report import load_saved_reports, render_eval_markdown, test_data_summary

    test_set = load_test_set(context)
    comparison_path = stage_dir("detypify") / COMPARISON_FILE
    comparison = json.loads(comparison_path.read_text()) if comparison_path.exists() else None
    summary_path = stage_dir("export") / "export_summary.json"
    package = json.loads(summary_path.read_text()) if summary_path.exists() else None
    markdown = render_eval_markdown(
        load_saved_reports(), test_data_summary(test_set), comparison, package
    )
    (context.output_dir / "EVAL.md").write_text(markdown, encoding="utf-8")
    (REPO_ROOT / "EVAL.md").write_text(markdown, encoding="utf-8")


def default_stages() -> list[Stage]:
    """The stages of the full pipeline, in dependency order."""
    from glyphsketch.charset import DEFAULT_CONFIG_PATH
    from glyphsketch.fonts import DEFAULT_MANIFEST_PATH
    from glyphsketch.prior import wikitext
    from glyphsketch.prior.sample import DEFAULT_CONFIG_PATH as PRIOR_CONFIG_PATH
    from glyphsketch.realdata.detexify import MAPPING_PATH as DETEXIFY_MAPPING_PATH
    from glyphsketch.realdata.omniglot import MAPPING_PATH as OMNIGLOT_MAPPING_PATH
    from glyphsketch.synth import augment, skeleton
    from glyphsketch.ucd.files import UNICODE_VERSION

    skeleton_module_path = Path(skeleton.__file__)
    augment_module_path = Path(augment.__file__)
    return [
        Stage(
            name="ucd",
            description=f"Download the pinned Unicode {UNICODE_VERSION} data files",
            run=run_ucd_stage,
            version=UNICODE_VERSION,
        ),
        Stage(
            name="charset",
            description="Select the candidate characters from the UCD",
            run=run_charset_stage,
            depends_on=("ucd",),
            version="1-" + file_fingerprint(DEFAULT_CONFIG_PATH),
        ),
        Stage(
            name="fonts",
            description="Download the pinned fonts and their licenses",
            run=run_fonts_stage,
            version="1-" + file_fingerprint(DEFAULT_MANIFEST_PATH),
        ),
        Stage(
            name="glyphs",
            description="Render every covered (character, font) pair and report coverage",
            run=run_glyphs_stage,
            depends_on=("charset", "fonts"),
            version="1",
        ),
        Stage(
            name="detexify",
            description="Download the Detexify dump (ODbL) and symbol list",
            run=run_detexify_stage,
        ),
        Stage(
            name="omniglot",
            description="Download the Omniglot stroke data (MIT)",
            run=run_omniglot_stage,
        ),
        Stage(
            name="uji",
            description="Download UJI Pen Characters v2 (CC BY 4.0)",
            run=run_uji_stage,
        ),
        Stage(
            name="realdata",
            description="Map real drawings to code points and report the data",
            run=run_realdata_stage,
            depends_on=("charset", "glyphs", "detexify", "omniglot", "uji"),
            version="1-"
            + file_fingerprint(DETEXIFY_MAPPING_PATH)
            + file_fingerprint(OMNIGLOT_MAPPING_PATH),
        ),
        Stage(
            name="confusables",
            description="Group characters whose glyphs look alike",
            run=run_confusables_stage,
            depends_on=("ucd", "charset", "glyphs"),
            version="4",
        ),
        Stage(
            name="wikiprior",
            description="Sample Wikipedia dumps and build the character-frequency prior",
            run=run_wikiprior_stage,
            depends_on=("ucd", "charset", "glyphs"),
            version="3-"
            + file_fingerprint(PRIOR_CONFIG_PATH)
            + file_fingerprint(Path(wikitext.__file__)),
        ),
        Stage(
            name="glyphstrokes",
            description="Extract pen strokes from every glyph render (skeletons)",
            run=run_glyphstrokes_stage,
            depends_on=("glyphs",),
            version="1-" + file_fingerprint(skeleton_module_path),
        ),
        Stage(
            name="indexdata",
            description="Prepare the index and test images (glyph renders, held-out drawings)",
            run=run_indexdata_stage,
            depends_on=("glyphs", "realdata"),
            version="1",
        ),
        # Only training (the Kaggle bundle) needs this slow stage; exports don't wait for it.
        Stage(
            name="encoderdata",
            description="Prepare encoder training images (synthetic and real drawings)",
            run=run_encoderdata_stage,
            depends_on=("glyphs", "glyphstrokes", "realdata"),
            version="2-" + file_fingerprint(augment_module_path),
        ),
        Stage(
            name="baselines",
            description="Evaluate the raw-pixel and HOG nearest-render baselines",
            run=run_baselines_stage,
            depends_on=("charset", "glyphs", "realdata", "confusables"),
            version="1",
        ),
        Stage(
            name="export",
            description="Package the encoder, index and metadata for the engines (int8)",
            run=run_export_stage,
            depends_on=(
                "charset",
                "glyphs",
                "glyphstrokes",
                "realdata",
                "confusables",
                "indexdata",
                "wikiprior",
            ),
            version=export_version(),
        ),
        Stage(
            name="detypify",
            description="Compare with Detypify on the test drawings of its symbols",
            run=run_detypify_stage,
            depends_on=("realdata", "charset", "confusables", "indexdata", "export"),
            version="1",
        ),
        Stage(
            name="evalreport",
            description="Write EVAL.md from the saved evaluation reports",
            run=run_evalreport_stage,
            depends_on=("realdata", "confusables", "baselines", "export", "detypify"),
            version="2",
        ),
    ]


def main(argv: Sequence[str] | None = None) -> int:
    pipeline = Pipeline(default_stages())
    parser = argparse.ArgumentParser(prog="python -m glyphsketch.pipeline", description=__doc__)
    parser.add_argument("targets", nargs="*", default=["all"], help="'all' or stage names")
    parser.add_argument("--force", action="store_true", help="re-run the named stages")
    parser.add_argument("--list", action="store_true", help="list the stages and exit")
    args = parser.parse_args(argv)

    if args.list:
        for stage in pipeline.stages.values():
            state = "up to date" if pipeline.is_up_to_date(stage) else "stale"
            print(f"{stage.name:<16} {state:<11} {stage.description}")
        return 0
    targets = list(pipeline.stages) if args.targets == ["all"] else args.targets
    if not targets:
        print("No stages are registered yet.")
        return 0
    pipeline.run(targets, force=args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
