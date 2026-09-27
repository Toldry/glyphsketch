# Third-party components

glyphsketch is licensed under the AGPL-3.0 (see `LICENSE`). This file records every font,
dataset and dependency the project uses, with its license and where it comes from. Each
license was read from the component's own source (its license file, package metadata or
download page), not assumed. The **Use** column says whether a component ends up in
what we distribute (the exported model, index and libraries) or is only used to build them.

`training/tests/test_third_party_record.py` fails if a package in `training/uv.lock` is
missing from the Python table below or is listed with a different version. After changing
dependencies, run `uv run python -m glyphsketch.tools.license_report` in `training/` and
update the table.

## Unicode data

| Component | Version | License | Source | Use |
|-----------|---------|---------|--------|-----|
| Unicode Character Database: `UnicodeData.txt`, `Blocks.txt`, `Scripts.txt`, `ScriptExtensions.txt`, `PropertyValueAliases.txt`, `DerivedAge.txt`, `PropList.txt`, `emoji/emoji-data.txt`, `emoji/emoji-variation-sequences.txt` | 18.0.0 | Unicode-3.0 (Unicode License V3) | https://www.unicode.org/Public/18.0.0/ucd/ | Character selection. Names, blocks and scripts derived from it are **shipped** in the charset metadata |
| Unicode security data (UTS #39): `confusables.txt`, `intentional.txt` | 18.0.0 | Unicode-3.0 (Unicode License V3) | https://www.unicode.org/Public/18.0.0/security/ | Confusable groups, **shipped** in derived form |

The license was read from https://www.unicode.org/license.txt, which the file headers
point to through https://www.unicode.org/terms_of_use.html. It requires the copyright and
permission notice to accompany copies, so the full text is kept in
`LICENSES/Unicode-3.0.txt` and will ship with the exported metadata. Each file's SHA-256
is pinned in `training/src/glyphsketch/ucd/files.py`.

## Fonts

Used at build time only: the pipeline renders glyphs from these fonts to make training
data and the glyph index. The font files themselves are not shipped. What ships is the
index, a set of embedding vectors computed from the renders. Each font file and its
license text are pinned by SHA-256 in `training/src/glyphsketch/resources/fonts.toml`,
and the `fonts` stage saves each font's license next to it in `$DATA_DIR/fonts/licenses/`.

How each license was verified:
- Google Fonts families: the `OFL.txt` in each family's directory at the pinned commit
  `23e54b51ddffbc7713c583748e3bd86f62b1fa4a` of https://github.com/google/fonts (every
  `METADATA.pb` also says `license: "OFL"`).
- DejaVu 2.37: `LICENSE` in the release archive (Bitstream Vera license and Arev fonts
  license, DejaVu changes in the public domain).
- GNU FreeFont 20120503: `COPYING` (GPL-3.0) and the font exception in `README`.
- Libertinus 7.051: `OFL.txt` in the release archive.

| Font | Version | License | Source | Style |
|------|---------|---------|--------|-------|
| Noto Sans | 2.015 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/notosans | sans |
| Noto Serif | 2.015 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/notoserif | serif |
| Noto Serif Italic | 2.013 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/notoserif | serif |
| Noto Sans Mono | 2.014 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/notosansmono | mono |
| Noto Sans Hebrew | 3.001 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/notosanshebrew | sans |
| Noto Serif Hebrew | 2.004 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/notoserifhebrew | serif |
| Noto Sans Arabic | 2.012 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/notosansarabic | sans |
| Noto Naskh Arabic | 2.021 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/notonaskharabic | serif |
| Noto Sans Math | 3.000 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/notosansmath | math |
| Noto Sans Symbols | 2.003 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/notosanssymbols | symbols |
| Noto Sans Symbols 2 | 2.008 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/notosanssymbols2 | symbols |
| STIX Two Text | 2.13 b171 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/stixtwotext | serif |
| STIX Two Text Italic | 2.13 b171 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/stixtwotext | serif |
| STIX Two Math | 2.12 b168a | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/stixtwomath | math |
| Andika | 6.101 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/andika | sans |
| Charis SIL | 6.101 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/charissil | serif |
| Charis SIL Italic | 6.101 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/charissil | serif |
| Gentium Plus | 6.101 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/gentiumplus | serif |
| Source Sans 3 | 3.052 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/sourcesans3 | sans |
| Source Serif 4 | 4.004 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/sourceserif4 | serif |
| IBM Plex Sans | 3.201 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/ibmplexsans | sans |
| IBM Plex Mono | 2.3 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/ibmplexmono | mono |
| IBM Plex Sans Hebrew | 1.2 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/ibmplexsanshebrew | sans |
| IBM Plex Sans Arabic | 1.101 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/ibmplexsansarabic | sans |
| Playpen Sans | 2.000 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/playpensans | handwriting |
| Playpen Sans Hebrew | 2.000 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/playpensanshebrew | handwriting |
| Playpen Sans Arabic | 2.000 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/playpensansarabic | handwriting |
| Aref Ruqaa | 1.003 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/arefruqaa | handwriting |
| Caveat | 2.000 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/caveat | handwriting |
| Bad Script | 2.000 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/badscript | handwriting |
| Marck Script | 1.002 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/marckscript | handwriting |
| Patrick Hand | 1.003 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/patrickhand | handwriting |
| Kalam | 2.001 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/kalam | handwriting |
| Indie Flower | 2.000 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/indieflower | handwriting |
| Comic Neue | 2.003 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/comicneue | handwriting |
| Pangolin | 1.101 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/pangolin | handwriting |
| Klee One | 1.100 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/kleeone | handwriting |
| DejaVu Sans | 2.37 | Bitstream-Vera AND LicenseRef-Arev-Fonts (DejaVu changes: public domain) | https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-2.37.zip | sans |
| DejaVu Serif | 2.37 | Bitstream-Vera AND LicenseRef-Arev-Fonts (DejaVu changes: public domain) | https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-2.37.zip | serif |
| DejaVu Sans Mono | 2.37 | Bitstream-Vera AND LicenseRef-Arev-Fonts (DejaVu changes: public domain) | https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-2.37.zip | mono |
| FreeSans | 0412.2268 | GPL-3.0-or-later WITH Font-exception-2.0 | https://ftp.gnu.org/gnu/freefont/freefont-otf-20120503.tar.gz | sans |
| FreeSerif | 0412.2263 | GPL-3.0-or-later WITH Font-exception-2.0 | https://ftp.gnu.org/gnu/freefont/freefont-otf-20120503.tar.gz | serif |
| FreeSerif Italic | 0412.2268 | GPL-3.0-or-later WITH Font-exception-2.0 | https://ftp.gnu.org/gnu/freefont/freefont-otf-20120503.tar.gz | serif |
| FreeMono | 0412.2268 | GPL-3.0-or-later WITH Font-exception-2.0 | https://ftp.gnu.org/gnu/freefont/freefont-otf-20120503.tar.gz | mono |
| Libertinus Sans | 7.051 | OFL-1.1 | https://github.com/alerque/libertinus/releases/download/v7.051/Libertinus-7.051.zip | sans |
| Libertinus Serif | 7.051 | OFL-1.1 | https://github.com/alerque/libertinus/releases/download/v7.051/Libertinus-7.051.zip | serif |
| Libertinus Serif Italic | 7.051 | OFL-1.1 | https://github.com/alerque/libertinus/releases/download/v7.051/Libertinus-7.051.zip | serif |
| Libertinus Math | 7.051 | OFL-1.1 | https://github.com/alerque/libertinus/releases/download/v7.051/Libertinus-7.051.zip | math |

## Datasets

Added in M3.

## Python packages (training pipeline)

None of these are shipped. They run the pipeline that produces the exported files.

<!-- python-packages:start -->
| Package | Version | License | Source | Use |
|---------|---------|---------|--------|-----|
| `ast-serialize` | 0.11.2 | MIT | https://github.com/mypyc/ast_serialize | dev: type checking (mypy) |
| `colorama` | 0.4.6 | BSD-3-Clause | https://github.com/tartley/colorama | dev: pytest on Windows only |
| `fonttools` | 4.66.0 | MIT | https://github.com/fonttools/fonttools | pipeline: cmap and outline checks |
| `iniconfig` | 2.3.0 | MIT | https://github.com/pytest-dev/iniconfig | dev: tests (pytest) |
| `librt` | 0.15.0 | MIT | https://github.com/mypyc/librt | dev: type checking (mypy) |
| `mypy` | 2.3.1 | MIT (bundled typeshed: Apache-2.0 and MIT) | https://github.com/python/mypy | dev: type checking |
| `mypy-extensions` | 1.1.0 | MIT | https://github.com/python/mypy_extensions | dev: type checking (mypy) |
| `numpy` | 2.5.3 | BSD-3-Clause (wheel also bundles OpenBLAS: BSD-3-Clause; libgfortran: GPL-3.0-or-later WITH GCC-exception-3.1; libquadmath: LGPL-2.1-or-later) | https://github.com/numpy/numpy | pipeline: arrays |
| `packaging` | 26.3 | Apache-2.0 OR BSD-2-Clause | https://github.com/pypa/packaging | dev: tests (pytest) |
| `pathspec` | 1.1.1 | MPL-2.0 | https://github.com/cpburnz/python-pathspec | dev: type checking (mypy) |
| `pillow` | 12.3.0 | MIT-CMU (wheel also bundles FreeType: FTL OR GPL-2.0-or-later, HarfBuzz: MIT, and image codecs under permissive licenses) | https://github.com/python-pillow/Pillow | pipeline: glyph rendering |
| `pluggy` | 1.6.0 | MIT | https://github.com/pytest-dev/pluggy | dev: tests (pytest) |
| `pygments` | 2.21.0 | BSD-2-Clause | https://github.com/pygments/pygments | dev: tests (pytest) |
| `pytest` | 9.1.1 | MIT | https://github.com/pytest-dev/pytest | dev: tests |
| `ruff` | 0.16.9 | MIT | https://github.com/astral-sh/ruff | dev: lint and formatting |
| `typing-extensions` | 4.16.0 | PSF-2.0 | https://github.com/python/typing_extensions | dev: type checking (mypy) |
<!-- python-packages:end -->

## Web library and demo

Added in M9.

## Android library and demo

Added in M11.

## CI and development environment

Build and development tools only. Nothing from them is shipped.

| Component | Version | License | Source |
|-----------|---------|---------|--------|
| GitHub Action `actions/checkout` | v7.0.1 (pinned by commit) | MIT | https://github.com/actions/checkout |
| GitHub Action `astral-sh/setup-uv` | v10.2.0 (pinned by commit) | MIT | https://github.com/astral-sh/setup-uv |
| Devcontainer base image `mcr.microsoft.com/devcontainers/base:ubuntu-24.04` | ubuntu-24.04 | MIT (image definition); Ubuntu packages under their own licenses | https://github.com/devcontainers/images |
| Python | 3.12 (Ubuntu 24.04) | PSF-2.0 | https://www.python.org/ |
| uv | 0.12.19 | MIT OR Apache-2.0 | https://github.com/astral-sh/uv |
| Node.js | 24 (NodeSource) | MIT | https://nodejs.org/ |
| OpenJDK | 21 (Ubuntu 24.04) | GPL-2.0-only WITH Classpath-exception-2.0 | https://openjdk.org/ |
| GitHub CLI | 2.x | MIT | https://github.com/cli/cli |
| Android SDK command-line tools and platform-tools | 16111833 | Android Software Development Kit License Agreement (build tool, not a dependency of the library) | https://developer.android.com/studio |
