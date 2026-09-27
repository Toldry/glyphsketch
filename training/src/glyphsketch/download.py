"""Checksum-verified downloads.

Every file the pipeline fetches is pinned by SHA-256, so a changed upstream file fails
loudly instead of silently changing the training data.
"""

import hashlib
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

USER_AGENT = "glyphsketch-pipeline/0.1 (offline handwriting recognizer research)"
CHUNK_SIZE = 1 << 20


class ChecksumMismatchError(RuntimeError):
    pass


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(
    url: str,
    destination: Path,
    expected_sha256: str,
    *,
    attempts: int = 3,
    timeout_seconds: float = 60.0,
) -> Path:
    """Download ``url`` to ``destination`` unless a file with the right checksum is there.

    The file is written to a temporary name first and renamed only after its checksum
    matches, so an interrupted or corrupted download never looks complete.
    """
    if destination.is_file() and sha256_of_file(destination) == expected_sha256:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".partial")
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            digest = hashlib.sha256()
            with (
                urllib.request.urlopen(request, timeout=timeout_seconds) as response,
                partial.open("wb") as output,
            ):
                while chunk := response.read(CHUNK_SIZE):
                    digest.update(chunk)
                    output.write(chunk)
            actual = digest.hexdigest()
            if actual != expected_sha256:
                partial.unlink(missing_ok=True)
                raise ChecksumMismatchError(
                    f"{url}: expected SHA-256 {expected_sha256}, got {actual}"
                )
            os.replace(partial, destination)
            return destination
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            last_error = error
            partial.unlink(missing_ok=True)
            if attempt < attempts:
                time.sleep(2.0 * attempt)
    raise RuntimeError(f"Failed to download {url} after {attempts} attempts") from last_error
