import hashlib
from pathlib import Path

import pytest

from glyphsketch.download import ChecksumMismatchError, download_file, sha256_of_file


def _source(tmp_path: Path, content: bytes) -> tuple[str, str]:
    path = tmp_path / "source.bin"
    path.write_bytes(content)
    return path.as_uri(), hashlib.sha256(content).hexdigest()


def test_downloads_and_verifies(tmp_path: Path) -> None:
    url, checksum = _source(tmp_path, b"glyph data")
    destination = download_file(url, tmp_path / "out" / "file.bin", checksum)
    assert destination.read_bytes() == b"glyph data"
    assert sha256_of_file(destination) == checksum


def test_checksum_mismatch_leaves_no_file(tmp_path: Path) -> None:
    url, _ = _source(tmp_path, b"tampered")
    destination = tmp_path / "file.bin"
    with pytest.raises(ChecksumMismatchError):
        download_file(url, destination, "0" * 64)
    assert not destination.exists()
    assert not destination.with_name("file.bin.partial").exists()


def test_existing_valid_file_is_not_downloaded_again(tmp_path: Path) -> None:
    content = b"already here"
    destination = tmp_path / "file.bin"
    destination.write_bytes(content)
    checksum = hashlib.sha256(content).hexdigest()
    missing_url = (tmp_path / "does-not-exist").as_uri()
    assert download_file(missing_url, destination, checksum) == destination


def test_existing_corrupt_file_is_replaced(tmp_path: Path) -> None:
    url, checksum = _source(tmp_path, b"good")
    destination = tmp_path / "file.bin"
    destination.write_bytes(b"corrupt")
    download_file(url, destination, checksum)
    assert destination.read_bytes() == b"good"
