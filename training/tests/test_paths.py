from pathlib import Path

import pytest

from glyphsketch.paths import (
    DATA_DIR_ENV_VAR,
    REPO_ROOT,
    DataDirNotConfiguredError,
    data_dir,
    stage_dir,
)


def test_data_dir_requires_the_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DATA_DIR_ENV_VAR, raising=False)
    with pytest.raises(DataDirNotConfiguredError):
        data_dir()


def test_data_dir_rejects_a_directory_inside_the_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DATA_DIR_ENV_VAR, str(REPO_ROOT / "data"))
    with pytest.raises(DataDirNotConfiguredError):
        data_dir()
    assert not (REPO_ROOT / "data").exists()


def test_data_dir_is_created_on_first_use(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "nested" / "data"
    monkeypatch.setenv(DATA_DIR_ENV_VAR, str(target))
    assert data_dir() == target.resolve()
    assert target.is_dir()


def test_stage_dir_lives_under_the_data_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(DATA_DIR_ENV_VAR, str(tmp_path))
    directory = stage_dir("charset")
    assert directory == tmp_path.resolve() / "charset"
    assert directory.is_dir()
