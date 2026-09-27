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

Added in M2.

## Datasets

Added in M3.

## Python packages (training pipeline)

None of these are shipped. They run the pipeline that produces the exported files.

<!-- python-packages:start -->
| Package | Version | License | Source | Use |
|---------|---------|---------|--------|-----|
| `ast-serialize` | 0.11.2 | MIT | https://github.com/mypyc/ast_serialize | dev: type checking (mypy) |
| `colorama` | 0.4.6 | BSD-3-Clause | https://github.com/tartley/colorama | dev: pytest on Windows only |
| `iniconfig` | 2.3.0 | MIT | https://github.com/pytest-dev/iniconfig | dev: tests (pytest) |
| `librt` | 0.15.0 | MIT | https://github.com/mypyc/librt | dev: type checking (mypy) |
| `mypy` | 2.3.1 | MIT (bundled typeshed: Apache-2.0 and MIT) | https://github.com/python/mypy | dev: type checking |
| `mypy-extensions` | 1.1.0 | MIT | https://github.com/python/mypy_extensions | dev: type checking (mypy) |
| `packaging` | 26.3 | Apache-2.0 OR BSD-2-Clause | https://github.com/pypa/packaging | dev: tests (pytest) |
| `pathspec` | 1.1.1 | MPL-2.0 | https://github.com/cpburnz/python-pathspec | dev: type checking (mypy) |
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
