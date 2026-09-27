"""Omniglot (https://github.com/brendenlake/omniglot), MIT license.

Each character of each alphabet was drawn by 20 people on Mechanical Turk. Stroke files
live at ``strokes_<set>/<Alphabet>/characterNN/<image id>_<drawer>.txt`` and contain
``START``, then ``x,y,t`` lines, with ``BREAK`` between strokes. The files use a y-up
("motor") convention, so y is negated here.

Only the alphabets in the v0 scope are used, through the hand-made mapping in
``resources/omniglot_unicode.tsv`` (alphabet, character number, code point). The drawer
number serves as the writer id within an alphabet.
"""

import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import numpy as np

from glyphsketch.charset import parse_code_point
from glyphsketch.download import download_file
from glyphsketch.paths import RESOURCES_DIR
from glyphsketch.realdata.samples import DrawingSample

DATASET_NAME = "omniglot"
MAPPING_PATH = RESOURCES_DIR / "omniglot_unicode.tsv"
COMMIT = "057f034baf2ecb8530bc5710e5a23584d2a519cc"
BASE_URL = f"https://raw.githubusercontent.com/brendenlake/omniglot/{COMMIT}/"
STROKE_ARCHIVES = {
    "strokes_background.zip": "c1e445d158fd74b6adf81f1387ebe051f5a23923bdb0c16f539d6e707ce056d4",
    "strokes_evaluation.zip": "17185a39049e62d6e6a26070fa5c58e5ce7dbaff826a9f78595bdd7881d2070b",
}
LICENSE_SHA256 = "2efb425d9850e7bce985f151dc2ee1f4485e926a3582e08fd879cd28eb0388f5"
_MEMBER_PATTERN = re.compile(r"^strokes_\w+/([^/]+)/character(\d+)/(\d+)_(\d+)\.txt$")


def download_omniglot(destination_dir: Path) -> None:
    for name, sha256 in STROKE_ARCHIVES.items():
        download_file(BASE_URL + "python/" + name, destination_dir / name, sha256)
    download_file(BASE_URL + "LICENSE", destination_dir / "LICENSE", LICENSE_SHA256)


def parse_stroke_file(text: str) -> list[np.ndarray]:
    """Parse ``START`` / ``x,y,t`` / ``BREAK`` text into strokes with y pointing down."""
    strokes: list[np.ndarray] = []
    current: list[tuple[float, float]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line in ("START", "BREAK", ""):
            if current:
                strokes.append(np.array(current, dtype=np.float32))
                current = []
            continue
        x, y, _time = line.split(",")
        current.append((float(x), -float(y)))
    if current:
        strokes.append(np.array(current, dtype=np.float32))
    return strokes


@dataclass(frozen=True)
class OmniglotMappingEntry:
    alphabet: str
    character_number: int
    code_point: int | None
    note: str


def load_mapping(path: Path = MAPPING_PATH) -> dict[tuple[str, int], OmniglotMappingEntry]:
    entries: dict[tuple[str, int], OmniglotMappingEntry] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        alphabet, number, code_point, note = (line.split("\t") + [""] * 4)[:4]
        entry = OmniglotMappingEntry(
            alphabet=alphabet,
            character_number=int(number),
            code_point=parse_code_point(code_point) if code_point else None,
            note=note,
        )
        entries[(alphabet, entry.character_number)] = entry
    return entries


def omniglot_samples(
    archive_dir: Path,
    mapping: dict[tuple[str, int], OmniglotMappingEntry],
    allowed_code_points: set[int],
) -> Iterator[DrawingSample]:
    for archive_name in STROKE_ARCHIVES:
        with zipfile.ZipFile(archive_dir / archive_name) as archive:
            for member in sorted(archive.namelist()):
                match = _MEMBER_PATTERN.match(member)
                if match is None:
                    continue
                alphabet, number, _image_id, drawer = match.groups()
                entry = mapping.get((alphabet, int(number)))
                if entry is None or entry.code_point not in allowed_code_points:
                    continue
                strokes = parse_stroke_file(archive.read(member).decode("utf-8"))
                if not strokes:
                    continue
                yield DrawingSample(
                    dataset=DATASET_NAME,
                    sample_id=PurePosixPath(member).stem,
                    writer=f"{alphabet}/drawer{drawer}",
                    label=f"{alphabet}/character{number}",
                    code_point=entry.code_point,
                    strokes=strokes,
                )
