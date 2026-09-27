"""THIRD_PARTY.md must list every locked Python and npm package with its locked version."""

import json
import re
import tomllib
from fnmatch import fnmatchcase

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


def table_rows(start: str, end: str) -> list[list[str]]:
    text = (REPO_ROOT / "THIRD_PARTY.md").read_text(encoding="utf-8")
    table = text.split(start, 1)[1].split(end, 1)[0]
    rows = []
    for line in table.splitlines():
        cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3 or cells[0] in ("Package", "") or set(cells[0]) <= {"-", ":"}:
            continue
        rows.append(cells)
    return rows


def recorded_package_versions() -> set[tuple[str, str]]:
    return {
        (normalize_package_name(row[0]), version.strip())
        for row in table_rows(TABLE_START, TABLE_END)
        for version in row[1].split(",")
    }


def test_every_locked_package_is_recorded_with_its_version() -> None:
    missing = locked_package_versions() - recorded_package_versions()
    assert not missing, f"Add these packages to THIRD_PARTY.md: {sorted(missing)}"


def test_no_stale_package_rows() -> None:
    stale = recorded_package_versions() - locked_package_versions()
    assert not stale, f"Remove or update these THIRD_PARTY.md rows: {sorted(stale)}"


NPM_TABLE_START = "<!-- npm-packages:start -->"
NPM_TABLE_END = "<!-- npm-packages:end -->"


def locked_npm_packages() -> set[tuple[str, str]]:
    lock = json.loads((REPO_ROOT / "web" / "package-lock.json").read_text(encoding="utf-8"))
    return {
        (path.split("node_modules/")[-1], info["version"])
        for path, info in lock["packages"].items()
        if path
    }


def test_every_locked_npm_package_is_recorded() -> None:
    rows = table_rows(NPM_TABLE_START, NPM_TABLE_END)
    unrecorded = {
        (name, version)
        for name, version in locked_npm_packages()
        if not any(fnmatchcase(name, row[0]) and version == row[1] for row in rows)
    }
    assert not unrecorded, f"Add these npm packages to THIRD_PARTY.md: {sorted(unrecorded)}"


def test_no_stale_npm_rows() -> None:
    locked = locked_npm_packages()
    stale = [
        row[:2]
        for row in table_rows(NPM_TABLE_START, NPM_TABLE_END)
        if not any(fnmatchcase(name, row[0]) and version == row[1] for name, version in locked)
    ]
    assert not stale, f"Remove or update these THIRD_PARTY.md npm rows: {stale}"
