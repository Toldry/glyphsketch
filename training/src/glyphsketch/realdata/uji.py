"""UJI Pen Characters, version 2 (UCI Machine Learning Repository), CC BY 4.0.

60 writers drew 97 characters (Latin letters in both cases including Spanish letters,
digits, punctuation, @, $, <, >, €) twice each with a pen on a Tablet PC. The format is::

    WORD <character> <trn|tst>_<site>_W<writer>-<repetition>
      NUMSTROKES <k>
      POINTS <n> # x1 y1 x2 y2 ...

Coordinates are screen units with y pointing down. The file uses CRLF line endings.
"""

import zipfile
from collections.abc import Iterator
from pathlib import Path

import numpy as np

from glyphsketch.download import download_file
from glyphsketch.realdata.samples import DrawingSample

DATASET_NAME = "uji"
ARCHIVE_NAME = "uji-pen-characters-v2.zip"
ARCHIVE_URL = "https://archive.ics.uci.edu/static/public/177/uji+pen+characters+version+2.zip"
ARCHIVE_SHA256 = "0881b522911b99d9922820289441b50fd3d307f71cd7f9cc70e86872424a5f90"
DATA_MEMBER = "ujipenchars2.txt"


def download_uji(destination_dir: Path) -> None:
    download_file(ARCHIVE_URL, destination_dir / ARCHIVE_NAME, ARCHIVE_SHA256)


def parse_uji_text(text: str) -> Iterator[tuple[str, str, int, list[np.ndarray]]]:
    """Yield (character, writer, repetition, strokes) for every sample."""
    lines = [line.rstrip("\r") for line in text.split("\n")]
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if not line.startswith("WORD "):
            continue
        _, character, sample_name = line.split(" ", 2)
        _split, site, writer_and_repetition = sample_name.strip().split("_", 2)
        writer_number, repetition = writer_and_repetition.split("-")
        stroke_count = int(lines[index].split()[1])
        index += 1
        strokes = []
        for _ in range(stroke_count):
            header, _, coordinates = lines[index].partition("#")
            index += 1
            point_count = int(header.split()[1])
            values = np.array(coordinates.split(), dtype=np.float32)
            if len(values) != 2 * point_count:
                raise ValueError(f"Bad point count in {sample_name}")
            strokes.append(values.reshape(-1, 2))
        yield character, f"{site}_{writer_number}", int(repetition), strokes


def uji_samples(archive_dir: Path, allowed_code_points: set[int]) -> Iterator[DrawingSample]:
    with zipfile.ZipFile(archive_dir / ARCHIVE_NAME) as archive:
        text = archive.read(DATA_MEMBER).decode("utf-8")
    for character, writer, repetition, strokes in parse_uji_text(text):
        if len(character) != 1 or ord(character) not in allowed_code_points or not strokes:
            continue
        yield DrawingSample(
            dataset=DATASET_NAME,
            sample_id=f"{writer}-{character}-{repetition}",
            writer=writer,
            label=character,
            code_point=ord(character),
            strokes=strokes,
        )
