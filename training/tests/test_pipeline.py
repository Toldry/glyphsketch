from pathlib import Path

import pytest

from glyphsketch.pipeline import Pipeline, Stage, StageContext


def _recording_stage(
    name: str, log: list[str], depends_on: tuple[str, ...] = (), version: str = "1"
) -> Stage:
    def run(context: StageContext) -> None:
        log.append(name)
        (context.output_dir / "output.txt").write_text(name, encoding="utf-8")

    return Stage(name=name, description=name, run=run, depends_on=depends_on, version=version)


def _three_stage_pipeline(log: list[str], render_version: str = "1") -> Pipeline:
    return Pipeline(
        [
            _recording_stage("download", log),
            _recording_stage("render", log, depends_on=("download",), version=render_version),
            _recording_stage("train", log, depends_on=("render",)),
        ]
    )


@pytest.mark.usefixtures("isolated_data_dir")
def test_runs_dependencies_first_and_caches_results() -> None:
    log: list[str] = []
    pipeline = _three_stage_pipeline(log)
    assert pipeline.run(["train"]) == ["download", "render", "train"]
    assert pipeline.run(["train"]) == []
    assert log == ["download", "render", "train"]


@pytest.mark.usefixtures("isolated_data_dir")
def test_forcing_a_stage_invalidates_downstream_stages() -> None:
    log: list[str] = []
    pipeline = _three_stage_pipeline(log)
    pipeline.run(["train"])
    pipeline.run(["render"], force=True)
    assert pipeline.run(["train"]) == ["train"]


@pytest.mark.usefixtures("isolated_data_dir")
def test_bumping_a_stage_version_reruns_it_and_everything_after_it() -> None:
    log: list[str] = []
    _three_stage_pipeline(log).run(["train"])
    assert _three_stage_pipeline(log, render_version="2").run(["train"]) == ["render", "train"]


def test_stage_output_goes_to_its_data_directory(isolated_data_dir: Path) -> None:
    log: list[str] = []
    _three_stage_pipeline(log).run(["download"])
    assert (isolated_data_dir / "download" / "output.txt").read_text(encoding="utf-8") == (
        "download"
    )


@pytest.mark.usefixtures("isolated_data_dir")
def test_failed_stage_is_not_marked_complete() -> None:
    def failing_run(context: StageContext) -> None:
        raise RuntimeError("boom")

    pipeline = Pipeline([Stage(name="flaky", description="flaky", run=failing_run)])
    with pytest.raises(RuntimeError):
        pipeline.run(["flaky"])
    assert not pipeline.is_up_to_date(pipeline.stages["flaky"])


def test_rejects_dependencies_that_are_not_registered_first() -> None:
    log: list[str] = []
    with pytest.raises(ValueError, match="must be registered first"):
        Pipeline([_recording_stage("train", log, depends_on=("render",))])


def test_rejects_unknown_targets() -> None:
    with pytest.raises(KeyError):
        Pipeline([]).execution_order(["nope"])
