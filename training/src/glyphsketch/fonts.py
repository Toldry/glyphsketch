"""The font manifest and its checksum-verified download.

Downloaded layout under the stage directory::

    archives/<archive file>     upstream release archives (DejaVu, FreeFont, Libertinus)
    files/<font id>.<ext>       one font file per manifest entry
    licenses/<font id>.txt      the license text that came with that font
"""

import hashlib
import tarfile
import tomllib
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse

from glyphsketch.download import ChecksumMismatchError, download_file
from glyphsketch.paths import RESOURCES_DIR

DEFAULT_MANIFEST_PATH = RESOURCES_DIR / "fonts.toml"
FONT_STYLES = ("sans", "serif", "mono", "handwriting", "math", "symbols")


@dataclass(frozen=True)
class ArchiveSpec:
    id: str
    url: str
    sha256: str

    @property
    def file_name(self) -> str:
        return PurePosixPath(unquote(urlparse(self.url).path)).name


@dataclass(frozen=True)
class FontSpec:
    id: str
    family: str
    style: str
    sha256: str
    license: str
    license_sha256: str
    url: str = ""
    license_url: str = ""
    archive: str = ""
    member: str = ""
    license_member: str = ""
    # Render only characters of these blocks (empty: every character the font has). Script
    # fonts bring their own Latin, digits and punctuation, which the text fonts cover already.
    blocks: tuple[str, ...] = ()

    @property
    def extension(self) -> str:
        source = self.member or unquote(urlparse(self.url).path)
        return PurePosixPath(source).suffix.lower()


@dataclass(frozen=True)
class FontManifest:
    google_fonts_commit: str
    archives: dict[str, ArchiveSpec]
    fonts: tuple[FontSpec, ...]

    def font(self, font_id: str) -> FontSpec:
        for spec in self.fonts:
            if spec.id == font_id:
                return spec
        raise KeyError(font_id)


class InvalidManifestError(ValueError):
    pass


def load_font_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> FontManifest:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    archives = {item["id"]: ArchiveSpec(**item) for item in raw.get("archive", [])}
    fonts = tuple(
        FontSpec(**{**item, "blocks": tuple(item.get("blocks", ()))}) for item in raw["font"]
    )
    ids = [spec.id for spec in fonts]
    if len(ids) != len(set(ids)):
        raise InvalidManifestError("Duplicate font ids in the manifest")
    for spec in fonts:
        if spec.style not in FONT_STYLES:
            raise InvalidManifestError(f"{spec.id}: unknown style {spec.style!r}")
        from_url = bool(spec.url and spec.license_url)
        from_archive = bool(spec.archive and spec.member and spec.license_member)
        if from_url == from_archive:
            raise InvalidManifestError(f"{spec.id}: give either url+license_url or archive+member")
        if from_archive and spec.archive not in archives:
            raise InvalidManifestError(f"{spec.id}: unknown archive {spec.archive!r}")
    return FontManifest(raw["google_fonts_commit"], archives, fonts)


def font_file_path(fonts_dir: Path, spec: FontSpec) -> Path:
    return fonts_dir / "files" / f"{spec.id}{spec.extension}"


def license_file_path(fonts_dir: Path, spec: FontSpec) -> Path:
    return fonts_dir / "licenses" / f"{spec.id}.txt"


def read_archive_member(archive_path: Path, member: str) -> bytes:
    if archive_path.name.endswith(".zip"):
        with zipfile.ZipFile(archive_path) as archive:
            return archive.read(member)
    with tarfile.open(archive_path) as archive:
        extracted = archive.extractfile(member)
        if extracted is None:
            raise KeyError(f"{member} is not a regular file in {archive_path.name}")
        return extracted.read()


def _write_verified(path: Path, data: bytes, expected_sha256: str, what: str) -> None:
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected_sha256:
        raise ChecksumMismatchError(f"{what}: expected SHA-256 {expected_sha256}, got {actual}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def download_fonts(fonts_dir: Path, manifest: FontManifest) -> None:
    """Download every manifest font and its license text into ``fonts_dir``."""
    archive_paths: dict[str, Path] = {}
    for archive in manifest.archives.values():
        archive_paths[archive.id] = download_file(
            archive.url, fonts_dir / "archives" / archive.file_name, archive.sha256
        )
    for spec in manifest.fonts:
        font_path = font_file_path(fonts_dir, spec)
        license_path = license_file_path(fonts_dir, spec)
        if spec.archive:
            archive_path = archive_paths[spec.archive]
            _write_verified(
                font_path, read_archive_member(archive_path, spec.member), spec.sha256, spec.id
            )
            _write_verified(
                license_path,
                read_archive_member(archive_path, spec.license_member),
                spec.license_sha256,
                f"{spec.id} license",
            )
        else:
            download_file(spec.url, font_path, spec.sha256)
            download_file(spec.license_url, license_path, spec.license_sha256)
