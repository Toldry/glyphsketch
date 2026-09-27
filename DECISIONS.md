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
