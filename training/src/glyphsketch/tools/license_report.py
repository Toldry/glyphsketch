"""Print license metadata for every package in ``uv.lock``, for updating THIRD_PARTY.md.

The report reads each installed distribution's own metadata and license files, so the
licenses in THIRD_PARTY.md come from the packages themselves. Packages that the lock
file only needs on other platforms are reported as not installed; check those by hand.

Usage: ``uv run python -m glyphsketch.tools.license_report``
"""

import importlib.metadata
import re
import sys
import tomllib
from dataclasses import dataclass

from glyphsketch.paths import TRAINING_DIR


@dataclass(frozen=True)
class PackageLicense:
    name: str
    version: str
    installed: bool
    license_expression: str
    license_classifiers: tuple[str, ...]
    license_files: tuple[str, ...]
    source_url: str


def locked_packages() -> list[tuple[str, str]]:
    lock = tomllib.loads((TRAINING_DIR / "uv.lock").read_text(encoding="utf-8"))
    packages = []
    for package in lock["package"]:
        source = package.get("source", {})
        if "editable" in source or "virtual" in source:
            continue
        packages.append((package["name"], package["version"]))
    return sorted(packages)


def _source_url(metadata: importlib.metadata.PackageMetadata) -> str:
    urls: list[str] = metadata.get_all("Project-URL") or []
    preferred = ("source", "repository", "source code", "code", "github", "homepage")
    by_label: dict[str, str] = {}
    for entry in urls:
        label, _, url = entry.partition(",")
        by_label[label.strip().lower()] = url.strip()
    for label in preferred:
        if label in by_label:
            return by_label[label]
    if urls:
        return next(iter(by_label.values()))
    return metadata.get("Home-page") or ""


def describe_package(name: str, version: str) -> PackageLicense:
    try:
        distribution = importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError:
        return PackageLicense(name, version, False, "", (), (), "")
    metadata = distribution.metadata
    expression = metadata.get("License-Expression") or ""
    if not expression:
        legacy = (metadata.get("License") or "").strip()
        expression = legacy.splitlines()[0][:80] if legacy else ""
    classifiers = tuple(
        classifier.removeprefix("License :: ")
        for classifier in metadata.get_all("Classifier") or []
        if classifier.startswith("License ::")
    )
    license_files = tuple(
        str(file)
        for file in distribution.files or []
        if re.search(r"(LICEN[CS]E|COPYING|NOTICE)", str(file), re.IGNORECASE)
    )
    return PackageLicense(
        name=name,
        version=distribution.version,
        installed=True,
        license_expression=expression,
        license_classifiers=classifiers,
        license_files=license_files,
        source_url=_source_url(metadata),
    )


def main() -> int:
    for name, version in locked_packages():
        info = describe_package(name, version)
        if not info.installed:
            print(f"{name} {version}: NOT INSTALLED HERE (check the source by hand)")
            continue
        marker = "" if info.version == version else f" (installed {info.version}!)"
        print(f"{name} {version}{marker}")
        print(f"  expression: {info.license_expression or '-'}")
        print(f"  classifiers: {', '.join(info.license_classifiers) or '-'}")
        print(f"  files: {', '.join(info.license_files) or '-'}")
        print(f"  source: {info.source_url or '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
