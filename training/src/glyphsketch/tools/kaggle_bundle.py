"""Pack what a Kaggle GPU run needs into one zip, to upload as a private Kaggle dataset.

The zip holds the ``glyphsketch`` package source (``code/``) and the stage files the M6
experiments read (``data/<stage>/``), plus ``MANIFEST.json`` with the git commit and a
SHA-256 per file. ``training/kaggle/glyphsketch_train.ipynb`` finds it under
``/kaggle/input``, trains on the GPU and writes a results zip laid out like ``$DATA_DIR``.

The data includes real drawings derived from Detexify (ODbL) and renders of the fonts, so
the Kaggle dataset must stay **private**: it is a working copy, not a redistribution.

Usage: ``uv run python -m glyphsketch.tools.kaggle_bundle`` (writes
``$DATA_DIR/kaggle/glyphsketch-kaggle.zip``).
"""

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from collections.abc import Sequence
from pathlib import Path

from glyphsketch.paths import PACKAGE_DIR, REPO_ROOT, data_dir

BUNDLE_NAME = "glyphsketch-kaggle.zip"
MANIFEST_NAME = "MANIFEST.json"
STAGE_FILES = {
    "charset": ("charset.json",),
    "confusables": ("groups.json",),
    "glyphs": ("glyph_table.npz",),
    "glyphstrokes": ("glyph_strokes.npz",),
    "realdata": ("samples.npz",),
    "indexdata": ("glyph_images.npy", "test_images.npy"),
    "encoderdata": (
        "synthetic_images.npy",
        "synthetic_code_points.npy",
        "real_train_images.npy",
        "real_train_code_points.npy",
    ),
}


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "describe", "--always", "--dirty"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip()


def bundle_entries(source_root: Path, package_dir: Path) -> list[tuple[Path, str]]:
    """(file on disk, name in the zip) pairs; raises if a stage file is missing."""
    entries = [
        (path, f"code/glyphsketch/{path.relative_to(package_dir).as_posix()}")
        for path in sorted(package_dir.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    ]
    missing = []
    for stage, names in STAGE_FILES.items():
        for name in names:
            path = source_root / stage / name
            if path.is_file():
                entries.append((path, f"data/{stage}/{name}"))
            else:
                missing.append(str(path))
    if missing:
        raise FileNotFoundError(
            "Run the pipeline first (encoderdata and its inputs); missing: " + ", ".join(missing)
        )
    return entries


def write_bundle(
    output: Path, source_root: Path, package_dir: Path = PACKAGE_DIR
) -> dict[str, str]:
    """Write the zip; return the manifest (zip name → SHA-256, plus the commit)."""
    entries = bundle_entries(source_root, package_dir)
    manifest = {"commit": git_commit()}
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path, name in entries:
            manifest[name] = sha256_of(path)
            bundle.write(path, name)
        bundle.writestr(MANIFEST_NAME, json.dumps(manifest, indent=1) + "\n")
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    output = args.output or data_dir() / "kaggle" / BUNDLE_NAME
    manifest = write_bundle(output, data_dir())
    size = output.stat().st_size / 1024**2
    print(f"Wrote {output} ({size:.0f} MB, {len(manifest) - 1} files, commit {manifest['commit']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
