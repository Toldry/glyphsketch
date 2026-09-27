from pathlib import Path

import pytest

from glyphsketch.paths import DATA_DIR_ENV_VAR


@pytest.fixture
def isolated_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point ``$DATA_DIR`` at an empty temporary directory for the duration of a test."""
    data_root = tmp_path / "data"
    monkeypatch.setenv(DATA_DIR_ENV_VAR, str(data_root))
    return data_root
