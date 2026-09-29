import json
import zipfile
from pathlib import Path

import pytest

from glyphsketch.tools.kaggle_bundle import MANIFEST_NAME, STAGE_FILES, sha256_of, write_bundle


def _fake_stages(root: Path) -> None:
    for stage, names in STAGE_FILES.items():
        (root / stage).mkdir(parents=True)
        for name in names:
            (root / stage / name).write_bytes(f"{stage}/{name}".encode())


def test_bundle_holds_code_data_and_a_manifest(tmp_path: Path) -> None:
    package = tmp_path / "package"
    (package / "model").mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "model" / "train.py").write_text("x = 1\n")
    (package / "__pycache__").mkdir()
    (package / "__pycache__" / "junk.pyc").write_bytes(b"")
    data = tmp_path / "data"
    _fake_stages(data)
    output = tmp_path / "bundle.zip"
    manifest = write_bundle(output, data, package)
    with zipfile.ZipFile(output) as bundle:
        names = set(bundle.namelist())
        assert json.loads(bundle.read(MANIFEST_NAME)) == manifest
    assert "code/glyphsketch/model/train.py" in names
    assert not any("__pycache__" in name for name in names)
    assert "data/encoderdata/synthetic_images.npy" in names
    assert manifest["data/realdata/samples.npz"] == sha256_of(data / "realdata" / "samples.npz")


def test_bundle_refuses_missing_stage_files(tmp_path: Path) -> None:
    data = tmp_path / "data"
    _fake_stages(data)
    (data / "indexdata" / "test_images.npy").unlink()
    with pytest.raises(FileNotFoundError, match=r"test_images\.npy"):
        write_bundle(tmp_path / "bundle.zip", data, tmp_path)
