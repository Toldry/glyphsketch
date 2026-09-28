"""The ``wikiprior`` stage: sample the dumps, count characters, combine into one prior.

Each language's counts are turned into frequencies over the characters it contains, with
add-``smoothing`` counts for every charset character, and the languages are averaged with
equal weight:

    prior(c) = mean over languages of (count(c) + s) / (total + s · N)

So a character that only one script uses (Cyrillic А) gets a prior from the few
languages that use it, and one that no sample contains still gets a small, non-zero
prior. The shipped value is ``log prior(c)``.

Emoji hardly occur in Wikipedia text, so every Extended_Pictographic character gets at
least the median log prior of the characters in regular use (those the sample contains at
least 100 times; about the level of ∫, ≤ or €): one flat value for all emoji
(DECISIONS.md, D34). The plain median of all characters would be the floor, because most
characters occur only a handful of times. An emoji that Wikipedia uses more often (©, ™,
‼) keeps its own value.
"""

import hashlib
import json
import math
from collections import Counter
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from glyphsketch.charset import CharacterRecord, format_code_point
from glyphsketch.parallel import default_workers, single_threaded_pool
from glyphsketch.prior.sample import (
    Chunk,
    PriorConfig,
    PriorLanguage,
    complete_streams,
    dump_file_url,
    dump_files,
    dump_status_url,
    fetch_json,
    fetch_range,
    plan_chunks,
)
from glyphsketch.prior.wikitext import count_characters

PRIOR_FILE = "prior.json"
REPORT_FILE = "frequency_prior.md"
DOWNLOAD_CONNECTIONS = 2  # dumps.wikimedia.org asks for no more than two at a time


@dataclass(frozen=True)
class DownloadedChunk:
    language: str
    chunk: Chunk
    path: Path


def chunk_path(cache_dir: Path, language: str, chunk: Chunk) -> Path:
    return cache_dir / language / f"{chunk.file_name}.{chunk.start}-{chunk.end}"


def download_samples(config: PriorConfig, cache_dir: Path) -> list[DownloadedChunk]:
    """Fetch every planned chunk not cached yet; save each dump's status JSON too."""
    planned: list[tuple[str, Chunk, Path]] = []
    for language in config.languages:
        status_path = cache_dir / language.code / "dumpstatus.json"
        if status_path.exists():
            status = json.loads(status_path.read_text(encoding="utf-8"))
        else:
            status = fetch_json(dump_status_url(language.code, config.dump_date))
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text(json.dumps(status, indent=1), encoding="utf-8")
        chunks = plan_chunks(dump_files(status), config.chunks_per_language, config.chunk_bytes)
        for chunk in chunks:
            planned.append((language.code, chunk, chunk_path(cache_dir, language.code, chunk)))

    def fetch(item: tuple[str, Chunk, Path]) -> None:
        language, chunk, path = item
        if path.exists():
            return
        url = dump_file_url(language, config.dump_date, chunk.file_name)
        data = fetch_range(url, chunk.start, chunk.end)
        partial = path.with_suffix(path.suffix + ".part")
        partial.write_bytes(data)
        partial.rename(path)

    missing = [item for item in planned if not item[2].exists()]
    print(f"  {len(planned)} chunks planned, {len(missing)} to download", flush=True)
    with ThreadPoolExecutor(DOWNLOAD_CONNECTIONS) as pool:
        for done, _ in enumerate(pool.map(fetch, missing), start=1):
            if done % 24 == 0 or done == len(missing):
                print(f"  downloaded {done}/{len(missing)}", flush=True)
    return [DownloadedChunk(language, chunk, path) for language, chunk, path in planned]


def count_chunk(path: Path) -> tuple[Counter[int], int, int]:
    """(code point counts, article pages, complete streams) of one downloaded chunk."""
    counts: Counter[int] = Counter()
    pages = streams = 0
    for stream in complete_streams(path.read_bytes()):
        stream_counts, stream_pages = count_characters(stream.decode("utf-8", errors="replace"))
        counts.update(stream_counts)
        pages += stream_pages
        streams += 1
    return counts, pages, streams


def log_prior(
    counts_by_language: dict[str, Counter[int]], code_points: Sequence[int], smoothing: float
) -> dict[int, float]:
    totals = {
        language: sum(counts[code_point] for code_point in code_points)
        for language, counts in counts_by_language.items()
    }
    prior = {}
    for code_point in code_points:
        frequencies = [
            (counts[code_point] + smoothing) / (totals[language] + smoothing * len(code_points))
            for language, counts in counts_by_language.items()
        ]
        prior[code_point] = math.log(sum(frequencies) / len(frequencies))
    return prior


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


IN_REGULAR_USE = 100  # occurrences in the sample


def raise_to_flat_prior(
    prior: dict[int, float], flat_code_points: set[int], totals: dict[int, int]
) -> tuple[dict[int, float], float]:
    """Give ``flat_code_points`` at least the median prior of the characters in regular use:
    those the sample contains at least ``IN_REGULAR_USE`` times (about ∫, ≤ or €)."""
    regular = [
        value
        for code_point, value in prior.items()
        if code_point not in flat_code_points and totals.get(code_point, 0) >= IN_REGULAR_USE
    ]
    level = float(np.median(regular)) if regular else min(prior.values(), default=0.0)
    raised = {
        code_point: max(value, level) if code_point in flat_code_points else value
        for code_point, value in prior.items()
    }
    return raised, level


def build_prior(
    config: PriorConfig,
    characters: Sequence[CharacterRecord],
    cache_dir: Path,
    flat_code_points: set[int] | None = None,
) -> dict[str, Any]:
    downloaded = download_samples(config, cache_dir)
    with single_threaded_pool(default_workers(len(downloaded))) as pool:
        results = pool.map(count_chunk, [item.path for item in downloaded], chunksize=1)
    code_points = [record.code_point for record in characters]
    in_charset = set(code_points)
    counts_by_language: dict[str, Counter[int]] = {
        lang.code: Counter() for lang in config.languages
    }
    languages: dict[str, dict[str, Any]] = {
        language.code: {
            "code": language.code,
            "scripts": list(language.scripts),
            "pages": 0,
            "streams": 0,
            "characters": 0,
            "chunks": [],
        }
        for language in config.languages
    }
    for item, (counts, pages, streams) in zip(downloaded, results, strict=True):
        summary = languages[item.language]
        summary["pages"] += pages
        summary["streams"] += streams
        summary["characters"] += sum(counts.values())
        summary["chunks"].append(
            {
                "file": item.chunk.file_name,
                "start": item.chunk.start,
                "end": item.chunk.end,
                "sha256": sha256_of(item.path),
            }
        )
        counts_by_language[item.language].update(
            {code_point: count for code_point, count in counts.items() if code_point in in_charset}
        )
    prior = log_prior(counts_by_language, code_points, config.smoothing)
    flat = (flat_code_points or set()) & set(code_points)
    totals: Counter[int] = Counter()
    for counts in counts_by_language.values():
        totals.update(counts)
    prior, flat_value = raise_to_flat_prior(prior, flat, totals)
    return {
        "flat_prior": {
            "rule": "Extended_Pictographic characters get at least the median log prior of "
            f"the characters the sample contains at least {IN_REGULAR_USE} times",
            "characters": len(flat),
            "log_prior": round(flat_value, 4),
        },
        "dump_date": config.dump_date,
        "source": "https://dumps.wikimedia.org/<language>wiki/<dump_date>/, "
        "pages-articles-multistream dumps",
        "smoothing": config.smoothing,
        "languages": list(languages.values()),
        "counts": {
            language: {format_code_point(cp): count for cp, count in sorted(counts.items())}
            for language, counts in counts_by_language.items()
        },
        "log_prior": {format_code_point(cp): round(value, 4) for cp, value in prior.items()},
    }


@dataclass(frozen=True)
class FrequencyPrior:
    log_prior: dict[int, float]
    languages: tuple[PriorLanguage, ...]
    dump_date: str

    @classmethod
    def load(cls, path: Path) -> "FrequencyPrior":
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            log_prior={int(key[2:], 16): value for key, value in raw["log_prior"].items()},
            languages=tuple(
                PriorLanguage(item["code"], tuple(item["scripts"])) for item in raw["languages"]
            ),
            dump_date=raw["dump_date"],
        )

    def scripts_of(self, language: str) -> tuple[str, ...]:
        for item in self.languages:
            if item.code == language:
                return item.scripts
        return ("Latin",)

    def minimum(self) -> float:
        return min(self.log_prior.values())


def render_report(prior: dict[str, Any], characters: Sequence[CharacterRecord]) -> str:
    by_code_point = {record.code_point: record for record in characters}
    log_values = {int(key[2:], 16): value for key, value in prior["log_prior"].items()}
    seen = {
        int(key[2:], 16)
        for counts in prior["counts"].values()
        for key, count in counts.items()
        if count > 0
    }
    lines = [
        "# Character-frequency prior",
        "",
        "Generated by the `wikiprior` stage; see DECISIONS.md (D25) for the method.",
        "",
        f"Source: Wikipedia pages-articles-multistream dumps of {prior['dump_date']}, "
        "sampled by byte range (https://dumps.wikimedia.org). Wikipedia text is licensed "
        "CC BY-SA 4.0 and GFDL; only character counts are derived from it.",
        "",
        "| Language | Scripts | Chunks | Articles | Characters counted |",
        "|----------|---------|-------:|---------:|-------------------:|",
    ]
    for language in prior["languages"]:
        lines.append(
            f"| {language['code']} | {', '.join(language['scripts'])} | "
            f"{len(language['chunks'])} | {language['pages']:,} | {language['characters']:,} |"
        )
    lines += [
        "",
        f"{len(seen):,} of {len(log_values):,} charset characters occur at least once in "
        "the sample.",
        "",
        "## Most frequent characters",
        "",
        "| Rank | Character | Code point | Name | log prior |",
        "|-----:|:---------:|------------|------|----------:|",
    ]
    ranked = sorted(log_values.items(), key=lambda item: -item[1])
    for rank, (code_point, value) in enumerate(ranked[:40], start=1):
        record = by_code_point[code_point]
        lines.append(
            f"| {rank} | {_display(record.char)} | {format_code_point(code_point)} | "
            f"{record.name} | {value:.2f} |"
        )
    lines += [
        "",
        "## Selected look-alikes and symbols",
        "",
        "| Character | Code point | Name | Script | log prior |",
        "|:---------:|------------|------|--------|----------:|",
    ]
    for char in "AΑАoοоxх×∫≤→∑Σ∞€αаəʃ":
        code_point = ord(char)
        if code_point in by_code_point:
            record = by_code_point[code_point]
            lines.append(
                f"| {_display(char)} | {format_code_point(code_point)} | {record.name} | "
                f"{record.script} | {log_values[code_point]:.2f} |"
            )
    return "\n".join(lines) + "\n"


def _display(char: str) -> str:
    return "\\|" if char == "|" else char
