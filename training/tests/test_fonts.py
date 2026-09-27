import hashlib
import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from conftest import real_stage_dir_or_skip
from glyphsketch.download import ChecksumMismatchError
from glyphsketch.fonts import (
    ArchiveSpec,
    FontManifest,
    FontSpec,
    InvalidManifestError,
    download_fonts,
    font_file_path,
    license_file_path,
    load_font_manifest,
)
from glyphsketch.render import GlyphChecker

# Every font license must be one of these (all compatible with AGPL-3.0, see THIRD_PARTY.md).
ALLOWED_FONT_LICENSES = {
    "OFL-1.1",
    "GPL-3.0-or-later WITH Font-exception-2.0",
    "Bitstream-Vera AND LicenseRef-Arev-Fonts (DejaVu changes: public domain)",
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_manifest_is_valid_and_uses_only_allowed_licenses() -> None:
    manifest = load_font_manifest()
    assert len(manifest.fonts) >= 40
    assert {spec.license for spec in manifest.fonts} <= ALLOWED_FONT_LICENSES
    assert len(manifest.google_fonts_commit) == 40
    for spec in manifest.fonts:
        assert len(spec.sha256) == 64 and len(spec.license_sha256) == 64
        if spec.url:
            assert manifest.google_fonts_commit in spec.url
            assert manifest.google_fonts_commit in spec.license_url


def test_manifest_has_several_styles_for_each_script_group() -> None:
    styles = {spec.style for spec in load_font_manifest().fonts}
    assert styles == {"sans", "serif", "mono", "handwriting", "math", "symbols"}


def test_manifest_rejects_fonts_without_a_source(tmp_path: Path) -> None:
    manifest_path = tmp_path / "fonts.toml"
    manifest_path.write_text(
        'google_fonts_commit = "x"\n[[font]]\nid = "a"\nfamily = "A"\nstyle = "sans"\n'
        f'sha256 = "{"0" * 64}"\nlicense = "OFL-1.1"\nlicense_sha256 = "{"0" * 64}"\n',
        encoding="utf-8",
    )
    with pytest.raises(InvalidManifestError, match="either url"):
        load_font_manifest(manifest_path)


def _zip_archive(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def _tar_archive(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def test_download_fonts_from_files_and_archives(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    direct_font, direct_license = b"direct font", b"direct license"
    (source / "Direct.ttf").write_bytes(direct_font)
    (source / "OFL.txt").write_bytes(direct_license)
    zip_bytes = _zip_archive({"pkg/Zipped.ttf": b"zipped font", "pkg/LICENSE": b"zip license"})
    tar_bytes = _tar_archive({"pkg/Tarred.otf": b"tarred font", "pkg/COPYING": b"tar license"})
    (source / "fonts.zip").write_bytes(zip_bytes)
    (source / "fonts.tar.gz").write_bytes(tar_bytes)
    manifest = FontManifest(
        google_fonts_commit="0" * 40,
        archives={
            "zip": ArchiveSpec("zip", (source / "fonts.zip").as_uri(), _sha256(zip_bytes)),
            "tar": ArchiveSpec("tar", (source / "fonts.tar.gz").as_uri(), _sha256(tar_bytes)),
        },
        fonts=(
            FontSpec(
                id="direct",
                family="Direct",
                style="sans",
                sha256=_sha256(direct_font),
                license="OFL-1.1",
                license_sha256=_sha256(direct_license),
                url=(source / "Direct.ttf").as_uri(),
                license_url=(source / "OFL.txt").as_uri(),
            ),
            FontSpec(
                id="zipped",
                family="Zipped",
                style="serif",
                sha256=_sha256(b"zipped font"),
                license="OFL-1.1",
                license_sha256=_sha256(b"zip license"),
                archive="zip",
                member="pkg/Zipped.ttf",
                license_member="pkg/LICENSE",
            ),
            FontSpec(
                id="tarred",
                family="Tarred",
                style="mono",
                sha256=_sha256(b"tarred font"),
                license="OFL-1.1",
                license_sha256=_sha256(b"tar license"),
                archive="tar",
                member="pkg/Tarred.otf",
                license_member="pkg/COPYING",
            ),
        ),
    )
    fonts_dir = tmp_path / "fonts"
    download_fonts(fonts_dir, manifest)
    assert font_file_path(fonts_dir, manifest.font("direct")).read_bytes() == direct_font
    assert font_file_path(fonts_dir, manifest.font("zipped")).name == "zipped.ttf"
    assert font_file_path(fonts_dir, manifest.font("tarred")).read_bytes() == b"tarred font"
    assert license_file_path(fonts_dir, manifest.font("tarred")).read_bytes() == b"tar license"


def test_download_fonts_rejects_a_tampered_archive_member(tmp_path: Path) -> None:
    zip_bytes = _zip_archive({"Font.ttf": b"unexpected", "LICENSE": b"license"})
    archive_path = tmp_path / "fonts.zip"
    archive_path.write_bytes(zip_bytes)
    manifest = FontManifest(
        google_fonts_commit="0" * 40,
        archives={"zip": ArchiveSpec("zip", archive_path.as_uri(), _sha256(zip_bytes))},
        fonts=(
            FontSpec(
                id="font",
                family="Font",
                style="sans",
                sha256=_sha256(b"expected"),
                license="OFL-1.1",
                license_sha256=_sha256(b"license"),
                archive="zip",
                member="Font.ttf",
                license_member="LICENSE",
            ),
        ),
    )
    with pytest.raises(ChecksumMismatchError):
        download_fonts(tmp_path / "fonts", manifest)


@pytest.mark.data
def test_real_fonts_are_downloaded_with_licenses() -> None:
    fonts_dir = real_stage_dir_or_skip("fonts", "files")
    for spec in load_font_manifest().fonts:
        assert font_file_path(fonts_dir, spec).is_file(), spec.id
        license_text = license_file_path(fonts_dir, spec).read_text(errors="replace").lower()
        if spec.license == "OFL-1.1":
            assert "open font license" in license_text, spec.id
        elif spec.license.startswith("GPL-3.0"):
            assert "gnu general public license" in license_text, spec.id
        else:
            assert "bitstream" in license_text, spec.id
        assert GlyphChecker(font_file_path(fonts_dir, spec)).cmap, spec.id
