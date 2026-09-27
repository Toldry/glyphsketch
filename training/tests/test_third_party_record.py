"""THIRD_PARTY.md must list every locked Python package with its locked version."""

import re
import tomllib

from glyphsketch.paths import REPO_ROOT, TRAINING_DIR

TABLE_START = "<!-- python-packages:start -->"
TABLE_END = "<!-- python-packages:end -->"


def normalize_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def locked_package_versions() -> set[tuple[str, str]]:
    lock = tomllib.loads((TRAINING_DIR / "uv.lock").read_text(encoding="utf-8"))
    locked: set[tuple[str, str]] = set()
    for package in lock["package"]:
        source = package.get("source", {})
        if "editable" in source or "virtual" in source:
            continue
        locked.add((normalize_package_name(package["name"]), package["version"]))
    return locked


def recorded_package_versions() -> set[tuple[str, str]]:
    text = (REPO_ROOT / "THIRD_PARTY.md").read_text(encoding="utf-8")
    table = text.split(TABLE_START, 1)[1].split(TABLE_END, 1)[0]
    recorded: set[tuple[str, str]] = set()
    for line in table.splitlines():
        cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3 or cells[0] in ("Package", "") or set(cells[0]) <= {"-", ":"}:
            continue
        for version in cells[1].split(","):
            recorded.add((normalize_package_name(cells[0]), version.strip()))
    return recorded


def test_every_locked_package_is_recorded_with_its_version() -> None:
    missing = locked_package_versions() - recorded_package_versions()
    assert not missing, f"Add these packages to THIRD_PARTY.md: {sorted(missing)}"


def test_no_stale_package_rows() -> None:
    stale = recorded_package_versions() - locked_package_versions()
    assert not stale, f"Remove or update these THIRD_PARTY.md rows: {sorted(stale)}"
