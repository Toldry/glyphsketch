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

## Wikipedia (character-frequency prior)

| Component | Version | License | Source | Use |
|-----------|---------|---------|--------|-----|
| Wikipedia pages-articles-multistream dumps of 18 languages (en, de, fr, es, it, pt, pl, cs, tr, vi, ru, uk, bg, sr, el, he, ar, fa), sampled: 24 byte ranges of 4 MiB per language | 2026-09-01 | CC-BY-SA-4.0 and GFDL (text) | https://dumps.wikimedia.org/ | Character counts only. The per-character log prior derived from them is **shipped**; no text is |

The license was read from https://dumps.wikimedia.org/legal.html ("all original textual
content is licensed under the GNU Free Documentation License (GFDL) and the Creative
Commons Attribution-Share-Alike 4.0 License"). What ships is one number per character, an
aggregate statistic over hundreds of millions of characters, not any of the text. The
exported metadata still credits Wikipedia as the source. The byte ranges and each chunk's
SHA-256 are recorded in `$DATA_DIR/wikiprior/prior.json`; the method is in DECISIONS.md
(D25) and `docs/reports/frequency_prior.md`.

## Evaluation only

| Component | Version | License | Source | Use |
|-----------|---------|---------|--------|-----|
| Detypify (`detypify-service` npm package: `train/model.onnx`, `train/infer.json`) | 0.3.0 | MIT | https://github.com/QuarticCat/detypify | Comparison in EVAL.md (M10). Downloaded by the `detypify` stage (pinned by SHA-256); **not shipped** |

The license was read from the repository's `LICENSE` at commit `1598f71` (MIT, Copyright
(c) 2024 QuarticCat); the package's `package.json` also says MIT.

## Fonts

Used at build time only: the pipeline renders glyphs from these fonts to make training
data and the glyph index. The font files themselves are not shipped. What ships is the
index, a set of embedding vectors computed from the renders. Each font file and its
license text are pinned by SHA-256 in `training/src/glyphsketch/resources/fonts.toml`,
and the `fonts` stage saves each font's license next to it in `$DATA_DIR/fonts/licenses/`.
The one exception is the Android demo app: it ships subsets of the Noto fonts and Klee One
(OFL-1.1) in `android/demo/src/main/assets/fonts/`, each with its license text, to show
characters the phone's fonts lack (DECISIONS.md, D38).

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
| Noto Emoji (monochrome) | 3.002 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/notoemoji | symbols |
| Noto Music | 2.003 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/notomusic | symbols |
| Noto Sans Egyptian Hieroglyphs | 2.002 | OFL-1.1 | https://github.com/google/fonts/tree/23e54b51ddff/ofl/notosansegyptianhieroglyphs | symbols (Egyptian Hieroglyphs block) |
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

Used for training and evaluation. None of the data is redistributed: the pipeline
downloads it (checksums pinned in `training/src/glyphsketch/realdata/`), and only the
trained model and the label mappings in `training/src/glyphsketch/resources/` are
published.

| Dataset | Version | License | Source | Use |
|---------|---------|---------|--------|-----|
| Detexify training data (`detexify.sql.gz`, `symbols.json`) | dump of 2016-09-17 (210,454 samples, 1,098 symbols) | ODbL-1.0 | https://github.com/kirel/detexify-data (links the Google Drive folder with the files) | Training and evaluation |
| Omniglot stroke data (`strokes_background.zip`, `strokes_evaluation.zip`) | commit `057f034` (2019-02-13) | MIT | https://github.com/brendenlake/omniglot | Training and evaluation (6 in-scope alphabets) |
| UJI Pen Characters, version 2 | UCI dataset 177 (2008) | CC-BY-4.0 | https://archive.ics.uci.edu/dataset/177/uji+pen+characters+version+2 | Training and evaluation |
| XML Entity Definitions for Characters (`unicode.xml`) | 2015 (David Carlisle, W3C Math WG) | W3C Software Notice and License (2002) | https://www.w3.org/2003/entities/2007xml/unicode.xml | LaTeX→Unicode rows of `detexify_unicode.tsv`, which is **shipped** in the repo (notice in `LICENSES/W3C-20021231.txt`) |

How each license was verified: the Detexify README and `odbl-10.txt` in
kirel/detexify-data; Omniglot's `LICENSE` at the pinned commit; the UJI dataset page on
the UCI repository ("licensed under a Creative Commons Attribution 4.0 International (CC BY
4.0) license"); the header of `unicode.xml`.

**Obligations for what we ship.** The trained model counts as a Produced Work under the
ODbL (see `PLAN.md`, decisions made), so it must carry a notice. The export (M8) and both
apps will include this text:

> This recognizer was trained in part on data from Detexify
> (http://detexify.kirelabs.org), made available under the Open Database License 1.0
> (https://opendatacommons.org/licenses/odbl/1-0/); on Omniglot (Brenden Lake, MIT
> License, https://github.com/brendenlake/omniglot); and on UJI Pen Characters v2
> (F. Prat, M. J. Castro, D. Llorens, A. Marzal and J. M. Vilar, CC BY 4.0,
> https://archive.ics.uci.edu/dataset/177).

## Python packages (training pipeline)

None of these are shipped. They run the pipeline that produces the exported files.

<!-- python-packages:start -->
| Package | Version | License | Source | Use |
|---------|---------|---------|--------|-----|
| `ast-serialize` | 0.11.2 | MIT | https://github.com/mypyc/ast_serialize | dev: type checking (mypy) |
| `colorama` | 0.4.6 | BSD-3-Clause | https://github.com/tartley/colorama | dev: pytest on Windows only |
| `filelock` | 4.0.4 | MIT | https://github.com/tox-dev/py-filelock | pipeline: dependency of torch |
| `flatbuffers` | 25.12.19 | Apache-2.0 | https://github.com/google/flatbuffers | export: dependency of onnxruntime |
| `fonttools` | 4.66.0 | MIT | https://github.com/fonttools/fonttools | pipeline: cmap and outline checks |
| `fsspec` | 2026.9.0 | BSD-3-Clause | https://github.com/fsspec/filesystem_spec | pipeline: dependency of torch |
| `imageio` | 2.37.4 | BSD-2-Clause | https://github.com/imageio/imageio | pipeline: dependency of scikit-image |
| `iniconfig` | 2.3.0 | MIT | https://github.com/pytest-dev/iniconfig | dev: tests (pytest) |
| `jinja2` | 3.1.6 | BSD-3-Clause | https://github.com/pallets/jinja | pipeline: dependency of torch |
| `lazy-loader` | 0.6 | BSD-3-Clause | https://github.com/scientific-python/lazy-loader | pipeline: dependency of scikit-image |
| `librt` | 0.15.0 | MIT | https://github.com/mypyc/librt | dev: type checking (mypy) |
| `markupsafe` | 3.0.3 | BSD-3-Clause | https://github.com/pallets/markupsafe | pipeline: dependency of jinja2 |
| `ml-dtypes` | 0.6.0 | Apache-2.0 (bundled Eigen code: MPL-2.0) | https://github.com/jax-ml/ml_dtypes | export: dependency of onnx |
| `mpmath` | 1.3.0 | BSD-3-Clause | https://github.com/mpmath/mpmath | pipeline: dependency of sympy |
| `mypy` | 2.3.1 | MIT (bundled typeshed: Apache-2.0 and MIT) | https://github.com/python/mypy | dev: type checking |
| `mypy-extensions` | 1.1.0 | MIT | https://github.com/python/mypy_extensions | dev: type checking (mypy) |
| `networkx` | 3.7 | BSD-3-Clause | https://github.com/networkx/networkx | pipeline: dependency of scikit-image and torch |
| `numpy` | 2.5.3 | BSD-3-Clause (wheel also bundles OpenBLAS: BSD-3-Clause; libgfortran: GPL-3.0-or-later WITH GCC-exception-3.1; libquadmath: LGPL-2.1-or-later) | https://github.com/numpy/numpy | pipeline: arrays |
| `onnx` | 1.23.0 | Apache-2.0 | https://github.com/onnx/onnx | export: ONNX reference model |
| `onnxruntime` | 1.30.0 | MIT (wheel bundles third-party code listed in its `ThirdPartyNotices.txt`) | https://github.com/microsoft/onnxruntime | export: checks the ONNX reference model |
| `packaging` | 26.3 | Apache-2.0 OR BSD-2-Clause | https://github.com/pypa/packaging | dev: tests (pytest) |
| `pathspec` | 1.1.1 | MPL-2.0 | https://github.com/cpburnz/python-pathspec | dev: type checking (mypy) |
| `pillow` | 12.3.0 | MIT-CMU (wheel also bundles FreeType: FTL OR GPL-2.0-or-later, HarfBuzz: MIT, and image codecs under permissive licenses) | https://github.com/python-pillow/Pillow | pipeline: glyph rendering |
| `pluggy` | 1.6.0 | MIT | https://github.com/pytest-dev/pluggy | dev: tests (pytest) |
| `protobuf` | 7.36.2 | BSD-3-Clause | https://github.com/protocolbuffers/protobuf | export: dependency of onnx and onnxruntime |
| `pygments` | 2.21.0 | BSD-2-Clause | https://github.com/pygments/pygments | dev: tests (pytest) |
| `pytest` | 9.1.1 | MIT | https://github.com/pytest-dev/pytest | dev: tests |
| `ruff` | 0.16.9 | MIT | https://github.com/astral-sh/ruff | dev: lint and formatting |
| `scikit-image` | 0.26.0 | BSD-3-Clause (a few files BSD-2-Clause or MIT) | https://github.com/scikit-image/scikit-image | pipeline: skeletonization |
| `scipy` | 1.18.1 | BSD-3-Clause (wheel also bundles OpenBLAS: BSD-3-Clause; libgfortran: GPL-3.0-or-later WITH GCC-exception-3.1; libquadmath: LGPL-2.1-or-later) | https://github.com/scipy/scipy | pipeline: image filtering |
| `setuptools` | 84.0.0 | MIT | https://github.com/pypa/setuptools | pipeline: dependency of torch |
| `sympy` | 1.14.0 | BSD-3-Clause | https://github.com/sympy/sympy | pipeline: dependency of torch |
| `tifffile` | 2026.9.20 | BSD-3-Clause | https://github.com/cgohlke/tifffile | pipeline: dependency of scikit-image |
| `torch` | 2.14.0+cpu, 2.14.0 | BSD-3-Clause (bundled third-party code: Apache-2.0, Apache-2.0 WITH LLVM-exception, BSD-2-Clause, BSD-3-Clause, BSL-1.0, MIT). CPU-only build from the PyTorch index; 2.14.0 is the macOS wheel | https://github.com/pytorch/pytorch | pipeline: encoder training |
| `typing-extensions` | 4.16.0 | PSF-2.0 | https://github.com/python/typing_extensions | dev: type checking (mypy); pipeline: dependency of torch |
<!-- python-packages:end -->

## Web library and demo (npm)

The library and demo have no runtime dependencies: nothing below is shipped. These are
development tools only (type-checking and building the demo). Tests use Node's built-in
test runner. `training/tests/test_third_party_record.py` checks this table against
`web/package-lock.json`; a `*` in a name covers a family of packages with the same
version and license.

<!-- npm-packages:start -->
| Package | Version | License | Source | Use |
|---------|---------|---------|--------|-----|
| `typescript` | 7.0.2 | Apache-2.0 (bundled library type definitions carry the notices in its `NOTICE.txt`: MIT, W3C, CC-BY-4.0 and others) | https://github.com/microsoft/TypeScript | dev: type-checking and compiling |
| `@typescript/typescript-*` | 7.0.2 | Apache-2.0 | https://github.com/microsoft/TypeScript | dev: the compiler binary for each platform (optional; npm installs the one it needs) |
| `@types/node` | 24.19.0 | MIT | https://github.com/DefinitelyTyped/DefinitelyTyped | dev: Node type definitions for tests and scripts |
| `undici-types` | 7.24.6 | MIT | https://github.com/nodejs/undici | dev: dependency of `@types/node` |
<!-- npm-packages:end -->

## Android library and demo

The library (`android/glyphsketch`) has **no runtime dependencies** besides the Kotlin
standard library. It ships the files in `export/` as assets. Licenses checked in each
artifact's POM or repository.

| Component | Version | License | Source | Use |
|-----------|---------|---------|--------|-----|
| Kotlin standard library | 2.4.20 | Apache-2.0 | https://github.com/JetBrains/kotlin | runtime (library and demo) |
| Jetpack Compose (BOM: `ui`, `material3` and their AndroidX dependencies) | BOM 2026.09.00 | Apache-2.0 | https://developer.android.com/jetpack/androidx | runtime, demo app only |
| `androidx.activity:activity-compose` | 1.13.0 | Apache-2.0 | https://developer.android.com/jetpack/androidx | runtime, demo app only |
| Gradle (wrapper and distribution) | 9.7.1 | Apache-2.0 | https://github.com/gradle/gradle | build |
| Android Gradle Plugin | 9.4.1 | Apache-2.0 | https://developer.android.com/build | build |
| Kotlin Compose compiler plugin | 2.4.20 | Apache-2.0 | https://github.com/JetBrains/kotlin | build |
| kotlinter (Gradle plugin) | 5.7.0 | Apache-2.0 | https://github.com/jeremymailen/kotlinter-gradle | build: lint and format |
| ktlint (used by kotlinter) | 1.8.0 | MIT | https://github.com/pinterest/ktlint | build: lint and format |
| JUnit | 4.13.2 | EPL-1.0 | https://github.com/junit-team/junit4 | tests only, not shipped |
| AndroidX Test (`androidx.test:runner`, `androidx.test.ext:junit`) | 1.7.0, 1.3.0 | Apache-2.0 | https://developer.android.com/jetpack/androidx | on-device tests only, not shipped |
| Gradle Maven Publish Plugin (`com.vanniktech.maven.publish`) | 0.37.0 | Apache-2.0 | https://github.com/vanniktech/gradle-maven-publish-plugin | build: publishing to Maven Central |
| ONNX Runtime for Android (`com.microsoft.onnxruntime:onnxruntime-android`) | 1.30.0 | MIT | https://github.com/microsoft/onnxruntime | benchmark app only (`android/benchmark`), for the comparison the brief asks for; not in the library or the demo |

## CI and development environment

Build and development tools only. Nothing from them is shipped.

| Component | Version | License | Source |
|-----------|---------|---------|--------|
| GitHub Action `actions/checkout` | v7.0.1 (pinned by commit) | MIT | https://github.com/actions/checkout |
| GitHub Action `astral-sh/setup-uv` | v10.2.0 (pinned by commit) | MIT | https://github.com/astral-sh/setup-uv |
| GitHub Action `actions/setup-java` | v6.0.1 (pinned by commit) | MIT | https://github.com/actions/setup-java |
| GitHub Action `actions/setup-node` | v7.0.0 (pinned by commit) | MIT | https://github.com/actions/setup-node |
| Devcontainer base image `mcr.microsoft.com/devcontainers/base:ubuntu-24.04` | ubuntu-24.04 | MIT (image definition); Ubuntu packages under their own licenses | https://github.com/devcontainers/images |
| Python | 3.12 (Ubuntu 24.04) | PSF-2.0 | https://www.python.org/ |
| uv | 0.12.19 | MIT OR Apache-2.0 | https://github.com/astral-sh/uv |
| Node.js | 24 (NodeSource) | MIT | https://nodejs.org/ |
| OpenJDK | 21 (Ubuntu 24.04) | GPL-2.0-only WITH Classpath-exception-2.0 | https://openjdk.org/ |
| GitHub CLI | 2.x | MIT | https://github.com/cli/cli |
| Android SDK command-line tools and platform-tools | 16111833 | Android Software Development Kit License Agreement (build tool, not a dependency of the library) | https://developer.android.com/studio |
