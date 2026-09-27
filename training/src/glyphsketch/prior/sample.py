"""Sample Wikipedia dumps by byte range, without downloading whole dumps.

A pages-articles *multistream* dump is a concatenation of independent bz2 streams of 100
pages each, so any byte range can be cut down to the complete streams inside it and
decompressed on its own. ``plan_chunks`` spreads the ranges evenly over a language's dump
(over all its parts, when the dump is split), and ``complete_streams`` recovers the
streams of one range.
"""

import bz2
import json
import time
import tomllib
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from glyphsketch.paths import RESOURCES_DIR

DEFAULT_CONFIG_PATH = RESOURCES_DIR / "wikipedia_prior.toml"
DUMPS_URL = "https://dumps.wikimedia.org"
USER_AGENT = "glyphsketch-training/0.1 (character-frequency sampling; python-urllib)"
STREAM_MAGIC = b"BZh91AY&SY"


@dataclass(frozen=True)
class PriorLanguage:
    code: str
    scripts: tuple[str, ...]


@dataclass(frozen=True)
class PriorConfig:
    dump_date: str
    chunks_per_language: int
    chunk_bytes: int
    smoothing: float
    languages: tuple[PriorLanguage, ...]


def load_prior_config(path: Path = DEFAULT_CONFIG_PATH) -> PriorConfig:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    return PriorConfig(
        dump_date=raw["dump_date"],
        chunks_per_language=raw["chunks_per_language"],
        chunk_bytes=raw["chunk_bytes"],
        smoothing=raw["smoothing"],
        languages=tuple(
            PriorLanguage(item["code"], tuple(item["scripts"])) for item in raw["language"]
        ),
    )


@dataclass(frozen=True)
class DumpFile:
    name: str
    size: int
    sha1: str


@dataclass(frozen=True)
class Chunk:
    file_name: str
    start: int
    end: int  # exclusive


def dump_status_url(language: str, date: str) -> str:
    return f"{DUMPS_URL}/{language}wiki/{date}/dumpstatus.json"


def dump_file_url(language: str, date: str, file_name: str) -> str:
    return f"{DUMPS_URL}/{language}wiki/{date}/{file_name}"


def _part_number(name: str) -> int:
    marker = "multistream"
    digits = name.split(marker, 1)[1].split(".", 1)[0]
    return int(digits) if digits.isdigit() else 0


def dump_files(status: dict[str, object]) -> list[DumpFile]:
    """The article dump's data files in order: the single file, or the numbered parts."""
    job = status["jobs"]["articlesmultistreamdump"]  # type: ignore[index]
    if job["status"] != "done":
        raise RuntimeError(f"Dump not finished: status {job['status']}")
    files = {
        name: info
        for name, info in job["files"].items()
        if "multistream" in name and "-index" not in name and ".xml" in name
    }
    single = [name for name in files if name.endswith("multistream.xml.bz2")]
    names = single or sorted(files, key=_part_number)
    return [DumpFile(name, int(files[name]["size"]), str(files[name]["sha1"])) for name in names]


def plan_chunks(files: list[DumpFile], count: int, chunk_bytes: int) -> list[Chunk]:
    """``count`` ranges centred on evenly spaced points of the concatenated files."""
    total = sum(file.size for file in files)
    chunks = []
    for index in range(count):
        position = int((index + 0.5) * total / count)
        offset = 0
        for file in files:
            if position < offset + file.size:
                local = position - offset
                start = max(0, min(local - chunk_bytes // 2, file.size - chunk_bytes))
                chunks.append(Chunk(file.name, start, min(file.size, start + chunk_bytes)))
                break
            offset += file.size
    return chunks


def _request(url: str, headers: dict[str, str] | None = None) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})


def fetch_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(_request(url), timeout=60) as response:
        result: dict[str, object] = json.load(response)
        return result


def fetch_range(url: str, start: int, end: int, attempts: int = 4) -> bytes:
    """Bytes ``start:end`` of ``url``; the server must answer 206 (partial content)."""
    for attempt in range(attempts):
        try:
            request = _request(url, {"Range": f"bytes={start}-{end - 1}"})
            with urllib.request.urlopen(request, timeout=120) as response:
                if response.status != 206:
                    raise RuntimeError(f"{url}: expected 206, got {response.status}")
                data: bytes = response.read()
            if len(data) != end - start:
                raise RuntimeError(f"{url}: got {len(data)} bytes, expected {end - start}")
            return data
        except (OSError, RuntimeError):
            if attempt == attempts - 1:
                raise
            time.sleep(5 * (attempt + 1))
    raise AssertionError("unreachable")


def complete_streams(data: bytes) -> Iterator[bytes]:
    """Decompressed contents of every bz2 stream that lies wholly inside ``data``."""
    position = data.find(STREAM_MAGIC)
    while position >= 0:
        decompressor = bz2.BZ2Decompressor()
        try:
            output = decompressor.decompress(data[position:])
        except OSError:  # a false match of the magic bytes
            position = data.find(STREAM_MAGIC, position + 1)
            continue
        if not decompressor.eof:
            return  # the stream runs past the end of the range
        yield output
        next_position = len(data) - len(decompressor.unused_data)
        position = data.find(STREAM_MAGIC, next_position)
