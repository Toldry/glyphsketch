import os

import pytest

from glyphsketch.parallel import THREAD_VARIABLES, default_workers, single_threaded_pool


def _thread_settings(_: int) -> dict[str, str | None]:
    return {name: os.environ.get(name) for name in THREAD_VARIABLES}


def test_workers_are_single_threaded_and_the_parent_is_unchanged() -> None:
    before = _thread_settings(0)
    with single_threaded_pool(2) as pool:
        settings = pool.map(_thread_settings, [0, 1])
    assert all(value == "1" for worker in settings for value in worker.values())
    assert _thread_settings(0) == before


def test_default_workers_respects_the_override_and_task_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GLYPHSKETCH_WORKERS", "5")
    assert default_workers() == 5
    assert default_workers(tasks=3) == 3
    monkeypatch.delenv("GLYPHSKETCH_WORKERS")
    assert 1 <= default_workers() <= max(1, (os.cpu_count() or 2) // 2)
