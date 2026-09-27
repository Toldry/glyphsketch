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
from typing import Any

from glyphsketch.paths import stage_dir

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


def default_stages() -> list[Stage]:
    """The stages of the full pipeline, in dependency order."""
    from glyphsketch.charset import DEFAULT_CONFIG_PATH
    from glyphsketch.ucd.files import UNICODE_VERSION

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
