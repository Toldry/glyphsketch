"""Where the pipeline reads and writes files.

Large artefacts (downloads, renders, synthetic data, checkpoints) live under ``$DATA_DIR``,
never in the repository. Small, reviewed inputs (block lists, manifests, hand-made
mappings) ship inside the package under ``resources/``.
"""

import os
from pathlib import Path

DATA_DIR_ENV_VAR = "DATA_DIR"

PACKAGE_DIR = Path(__file__).resolve().parent
RESOURCES_DIR = PACKAGE_DIR / "resources"
TRAINING_DIR = PACKAGE_DIR.parent.parent
REPO_ROOT = TRAINING_DIR.parent


class DataDirNotConfiguredError(RuntimeError):
    """Raised when ``$DATA_DIR`` is unset, so outputs never land in the repo by accident."""


def data_dir() -> Path:
    """Return the root directory for large pipeline artefacts, creating it if needed."""
    value = os.environ.get(DATA_DIR_ENV_VAR, "").strip()
    if not value:
        raise DataDirNotConfiguredError(
            f"Set ${DATA_DIR_ENV_VAR} to a directory outside the repository "
            "(the devcontainer sets it to /data)."
        )
    root = Path(value).expanduser().resolve()
    if root == REPO_ROOT or REPO_ROOT in root.parents:
        raise DataDirNotConfiguredError(
            f"${DATA_DIR_ENV_VAR}={root} is inside the repository; point it elsewhere."
        )
    root.mkdir(parents=True, exist_ok=True)
    return root


def stage_dir(stage_name: str) -> Path:
    """Return (and create) the cache directory of one pipeline stage."""
    directory = data_dir() / stage_name
    directory.mkdir(parents=True, exist_ok=True)
    return directory
