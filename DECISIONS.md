# Design decisions

A running log of non-trivial design decisions and trade-offs, oldest first. Each entry says
what was decided, what else was considered, and why. When a later entry overrides an
earlier one, the earlier entry stays and gets a note pointing to its replacement.

The approved plan (`PLAN.md`, section 1) already records the big changes to the brief's
approach: raster input without stroke order, two index options, confusable-masked
negatives, a zero-shot split, pure inference engines and web first. They are not repeated
here.

---

## D1. License: AGPL-3.0-only (M0, 2026-09-27)

**Decision.** The repository is licensed `AGPL-3.0-only`, with the canonical text from
gnu.org in `LICENSE`.

**Alternatives.** `AGPL-3.0-or-later`.

**Why.** Thumb-Key's F-Droid metadata declares `License: AGPL-3.0-only`, and the brief asks
for AGPL-3.0. Using the same identifier avoids any question when the library is merged into
Thumb-Key. Relicensing to "or later" stays possible while the project has a single author.

## D2. Repository layout (M0, 2026-09-27)

**Decision.**

| Path | Contents |
|------|----------|
| `training/` | Python package `glyphsketch` (src layout) with the whole pipeline, tests, `uv.lock` |
| `training/src/glyphsketch/resources/` | Small reviewed inputs: block lists, font manifest, hand-made mappings |
| `export/` | Exported model, index and charset metadata consumed by the engines |
| `web/` | TypeScript engine library and the Vite demo |
| `android/` | Kotlin engine library and the Compose demo (last milestone) |
| `docs/` | Brief and longer write-ups |

Large artefacts (downloads, renders, synthetic data, checkpoints) live under `$DATA_DIR`.
`glyphsketch.paths.data_dir()` refuses to run when `$DATA_DIR` is unset or points inside
the repository, so a misconfigured run cannot fill the repo with generated files.

**Why.** One Python package keeps the pipeline importable from tests and from the future
Kaggle notebook. Small hand-made inputs live in the package so they are versioned with
the code that reads them.

## D3. Python tooling: uv, ruff, mypy, pytest (M0, 2026-09-27)

**Decision.** `training/` uses uv with a committed `uv.lock`, Python 3.12 (the system Python
of Ubuntu 24.04 in the devcontainer), ruff for lint and formatting (line length 100), mypy
with `disallow_untyped_defs` to enforce type hints, and pytest. Ruff's `ANN` rules and
mypy both run in CI.

**Alternatives.** pip-tools or Poetry for locking; black and flake8 instead of ruff;
pyright instead of mypy.

**Why.** The devcontainer already ships uv, and a single `uv.lock` pins every transitive
dependency for reproducibility. Ruff replaces several tools with one fast binary. mypy is
the reference type checker and runs well without a Node toolchain.

## D4. CI: one GitHub Actions job, actions pinned by commit (M0, 2026-09-27)

**Decision.** `.github/workflows/ci.yml` runs `uv sync --locked`, `ruff check`,
`ruff format --check`, `mypy` and `pytest` on `ubuntu-24.04`. Actions are pinned by commit
SHA with the release tag in a comment. Tests never download anything. Fixtures are either
tiny files in the repo or generated inside the test (for example fonts built with
fontTools' `FontBuilder`). Tests that need real data in `$DATA_DIR` carry the `data` marker
and are skipped when the data is missing. Web and Android jobs are added in M9 and M11.

**Why.** Pinning by SHA prevents a moved tag from changing what CI runs. Tests that don't
depend on the network are fast and don't break when an upstream server is down.

## D5. THIRD_PARTY.md is checked against `uv.lock` (M0, 2026-09-27)

**Decision.** A test compares every package and version in `uv.lock` with the Python table
in `THIRD_PARTY.md` and fails on missing or stale rows. `glyphsketch.tools.license_report`
prints each installed package's declared license and license files to help update the
table.

**Why.** The brief requires every dependency to be recorded with a license verified from
the source. Transitive dependencies are easy to forget, and the test makes forgetting one
fail CI.

## D6. Unicode 18.0.0, pinned by checksum (M1, 2026-09-27)

**Decision.** The pipeline uses Unicode 18.0.0, the latest release (published 2026-09-01).
Eleven files are pinned by SHA-256 in `glyphsketch/ucd/files.py`: the UCD files the charset
needs, plus `confusables.txt` and `intentional.txt` from the same release for the homoglyph
work in M3 and M7. `download.download_file` writes to a temporary name and renames only after
the checksum matches.

**Why.** A silent upstream change would change the training data. Taking the security data
from the same release keeps character properties and confusable data consistent.

**Checks.** A data test compares every parsed name with Python's `unicodedata` (Unicode
15.0). All 143k shared names match. Two general categories changed after 15.0 (U+0295 ʕ
became Lo, U+1171E became Mc), and the test lists them explicitly.

## D7. The v0 block list (M1, 2026-09-27)

**Decision.** `resources/charset_v0.toml` lists 48 blocks in nine groups: Latin (with IPA,
phonetic extensions and modifier letters), Greek, Cyrillic, Hebrew, Arabic, punctuation and
letterlike symbols, mathematics, arrows, and symbols. Inside those blocks the builder drops
general categories Cn, Co, Cc, Cf, Zs, Zl, Zp, Cs, Mn and Me, and characters with the
`Deprecated` property. U+FDFC RIAL SIGN is added explicitly because its block (Arabic
Presentation Forms-A) is otherwise excluded.

Result: **6,454 candidate characters** (the plan estimated 8–12k), before the font
coverage filter in M2. By group: Latin 1,697, mathematics 1,685 (997 of them Mathematical
Alphanumeric Symbols), symbols 798, punctuation and letterlike 553, arrows 510, Cyrillic
450, Greek 368, Arabic 356, Hebrew 37.

**Left out, and why.**
- Box Drawing, Block Elements, Braille Patterns: grids of near-identical shapes that
  people don't draw by hand.
- Alphabetic and Arabic Presentation Forms, Halfwidth and Fullwidth Forms: compatibility
  forms of characters already in the set. A keyboard should insert the base character.
- Emoji pictograph blocks (U+1F300 onwards), Geometric Shapes Extended and Supplemental
  Arrows-C: not in the brief's v0 list, and mostly emoji or obscure.
- CJK: planned as an optional index pack (M12).

**Deprecated characters** (4 in these blocks, e.g. U+0149 ŉ) are dropped: Unicode
recommends against using them.

**Mathematical Alphanumeric Symbols are included.** Styled letters such as 𝔄, 𝒜 and 𝔸 are
what math users most often look up. Note for M7: `confusables.txt` maps all of them to the
plain letters, including fraktur and script forms that look quite different, so confusable
groups must be checked visually (see M2 and M7) instead of taken from `confusables.txt`
unchanged.

**No spacing combining marks (Mc)** exist in these blocks, so the exclusion list matches
the plan (Mn and Me only) with no special case.

## D8. The emoji rule is enforced by the font coverage stage (M2) (M1, 2026-09-27)

**Decision.** `charset.json` marks the 60 characters with `Emoji_Presentation=Yes` (⌚, ☕,
♈, ⚡, ✅, ❌, ⭐, …) with `emoji_presentation: true`. The rule "keep only emoji-presentation
characters that have a text-presentation glyph in a free font" is applied in M2, where the
coverage check knows which fonts have which glyphs. A text-presentation glyph means a glyph
in one of the manifest's monochrome text fonts. The manifest contains no emoji fonts, not
even the monochrome Noto Emoji. Every character without a glyph in any manifest font is
dropped there, so the emoji rule is a special case of the coverage filter.

**Alternatives.** Counting monochrome Noto Emoji as a text font would make the rule
meaningless, since it has a glyph for every emoji. Downloading fonts in M1 just for this
check would duplicate M2.
