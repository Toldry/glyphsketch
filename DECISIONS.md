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

## D9. Font set: 48 text fonts, 13 of them handwriting-style (M2, 2026-09-27)

**Decision.** `resources/fonts.toml` pins 48 font files (each file and its license text by
SHA-256): 37 from a fixed commit of google/fonts (Noto, STIX Two, SIL's Andika, Charis and
Gentium, Source, IBM Plex and 13 informal or handwriting-style fonts), plus DejaVu
2.37, GNU FreeFont 20120503 and Libertinus 7.051 from their release archives. Styles are
recorded so training can balance them: sans, serif, mono, handwriting, math, symbols.

**Why these.** Coverage and variety of letterforms matter more than the number of fonts:
- SIL fonts, Noto, DejaVu and FreeSerif cover the IPA and extended Latin blocks.
- Four math fonts (Noto Sans Math, STIX Two Math, Libertinus Math, FreeSerif) cover the
  math blocks, including all Mathematical Alphanumeric Symbols.
- Handwriting-style fonts supply the letterforms people actually write, which print fonts
  lack. Examples: single-storey a and g (Andika, Playpen, Caveat), Russian cursive (Bad
  Script, Marck Script, Caveat), cursive Hebrew (Playpen Sans Hebrew uses cursive
  letterforms), and Ruqʿah, the everyday Arabic handwriting style (Aref Ruqaa).
- True italics (Noto Serif, STIX Two, Charis, FreeSerif, Libertinus) add cursive forms.
  Oblique-only styles are skipped because synthetic shear covers them.

**Left out.** Emoji fonts (D8). DejaVu Math TeX Gyre (mixed Bitstream, public-domain and
AMSFonts terms, and four other math fonts cover the same characters). GNU Unifont: it is
a 16×16 bitmap design, and the only characters it would add are brand-new ones (D12).
Small-caps and decorative faces (Amatic SC, Libertinus Keyboard/Initials), since
small-caps lowercase would teach wrong shapes. Bold weights, since the synthetic
generator varies stroke width anyway.

## D10. What counts as a real glyph (M2, 2026-09-27)

**Decision.** A (character, font) pair is rendered only if all of these hold:
1. The font's best cmap maps the code point to a glyph.
2. That glyph is not glyph 0 / `.notdef`.
3. It is not shared by more than 8 code points (a placeholder glyph).
4. Its decomposed outline has at least one segment (not empty).
5. Its outline differs from the `.notdef` outline (not a copy of the missing-glyph box).
6. The render has ink.

Pillow draws with the single font file it is given, using FreeType with the basic layout
engine (no libraqm, so no shaping or font fallback). A glyph from another font can never
appear. Variable fonts are set to weight 400 on their weight axis, other axes at their
defaults.

**Result.** Across the 48 fonts only three glyphs were rejected, all empty outlines: ARABIC
TATWEEL in Aref Ruqaa, U+1D03 in FreeSans and U+1DB4 in Libertinus Serif Italic. The
checks are unit-tested with fonts built by fontTools' `FontBuilder`.

## D11. Render normalization: ink box scaled to 112 px in a 128 px square (M2, 2026-09-27)

**Decision.** Each glyph is drawn once at 256 px/em to measure its ink box, then drawn
again at the size that makes the longer side of the ink box exactly 112 px, and centered
in a 128×128 grayscale image (aspect ratio kept). The ink box in em units (relative to the
origin and baseline) is stored alongside each render.

**Alternatives.** Rendering at a fixed em size keeps relative size and position (a period
stays a small dot low on the line), but drawn input has no baseline or em box to compare
against. People draw a character to fill the drawing area, so size normalization is the
realistic match. Resampling a fixed-size render would blur small glyphs. Re-rendering at
the target size keeps outlines sharp.

**Consequences.** Characters that differ mainly in size or position (`.` `·` `•` `●`, or `,`
`'`) look alike after normalization. The confusable grouping and frequency prior (M7) have
to handle them. The stored em-unit ink boxes allow a size- and position-aware experiment
later. The drawing preprocessing (M5, M9) must use the same 112-in-128 framing (7/8).

## D12. Characters no text font covers are dropped (M2, 2026-09-27)

**Decision.** 293 of the 6,454 candidates have no real glyph in any of the 48 fonts and are
dropped, leaving **6,161 characters** and **74,085 renders** (12 fonts per character on
average, median 48 for Basic Latin, 1–2 for some symbol and Arabic extension blocks).
Almost all dropped characters are recent additions to Unicode (Unicode 15–18): Latin
Extended-G (157), Cyrillic Extended-D (62), Arabic Extended-C (39), and the three currency
signs new in Unicode 18.

**Why.** No device font can display these characters yet either, so a keyboard couldn't
show them in a candidate tile. When fonts add them, re-running the pipeline brings them
in with no new handwriting data. That is the main property of the design.

**Emoji rule outcome.** All 60 emoji-presentation characters have a text glyph in at least
one text font (mostly Noto Sans Symbols 2, DejaVu Sans and FreeSerif), so all stay.

The full per-block and per-font numbers are in `docs/reports/glyph_coverage.md`, which the
`glyphs` stage regenerates.

## D13. Real data: Detexify, Omniglot and UJI Pen Characters (M3, 2026-09-27)

**Decision.** Three openly licensed stroke datasets, 223,038 samples of 998 characters in
the glyph set:

| Dataset | License | Samples used | Characters | Writers |
|---------|---------|-------------:|-----------:|--------:|
| Detexify (LaTeX symbols, drawn on a web canvas) | ODbL 1.0 | 207,758 | 786 | 1,290 pseudo-writers (days) |
| Omniglot (6 alphabets, Mechanical Turk) | MIT | 3,640 | 180 | 120 |
| UJI Pen Characters v2 (Latin, digits, punctuation, Tablet PC) | CC BY 4.0 | 11,640 | 97 | 60 |

UJI was added beyond the brief because it is the only openly licensed online dataset we
found with writer ids for plain Latin letters, digits and punctuation, which Detexify
lacks. Detexify is dominated by math: Mathematical Operators and Greek make up half of
all samples. Hebrew and Arabic have real data only from Omniglot: 440 and 760 samples.

**Not used.** HASYv2, because most of it is Detexify data again. Other candidates
(CROHME, MathWriting, EMNIST, IAM-OnDB, CoMNIST) were not evaluated in M3. Each would
need its license verified from the source first, and some are known to be non-commercial
or registration-only.

## D14. Detexify → Unicode mapping, reviewed drawing by drawing (M3, 2026-09-27)

**Decision.** `resources/detexify_unicode.tsv` maps all 1,098 Detexify keys. It is
generated by `glyphsketch.tools.detexify_mapping` from three sources:
- 502 keys from W3C's `unicode.xml`. When a command names several characters, the
  unicode-math reading wins.
- 174 keys by rule: styled alphabets including the Letterlike "holes" (ℝ, ℭ, ℬ, …), and
  upright Greek.
- 360 keys from a hand-written table.

62 keys have no single-code-point equivalent (e.g. `\ngeqq`, pictograms like `\Faxmachine`)
and are not used. 8 keys map outside the glyph set.

**Review.** Every key was checked visually. Sheets show each key's font glyph next to six
drawings from the dataset (`glyphsketch.tools.mapping_sheets`, 28 sheets). The review
found 16 wrong mappings, now fixed, e.g. `\centerdot` is a small filled square in
amssymb (▪, not ·), `\textperiodcentered` is · (unicode.xml says ˙), `\textdoublepipe` is ǁ
(unicode.xml says ǂ), marvosym's `\Pluto` is the astrological ⯓ while wasysym's `\pluto` is
♇, and `\Pfund` is ℔. LaTeX's `\phi` is ϕ and `\varphi` is φ, `\epsilon` is ϵ and
`\varepsilon` is ε.

**Noise.** Some keys contain junk drawings, e.g. squares and scribbles for `\cdotp`, or
someone writing "LIMS" for `/`. They stay in the data: they are rare, and removing them
by hand would bias the evaluation.

## D15. Omniglot mapped by hand (M3, 2026-09-27)

**Decision.** `resources/omniglot_unicode.tsv` maps 182 of the 190 in-scope Omniglot
characters to code points after looking at the drawings:
- Latin, Greek and Cyrillic: the lowercase letters in alphabetical order.
- Hebrew: the non-final letter forms.
- Jawi (Malay): the standard 40-letter order, with Jawi's keheh-based kaf (ک) and ga (ݢ).
- Old Church Slavonic: capital code points where the drawn shape is the capital.

Eight characters are excluded, each with a note. Two Jawi drawings are ambiguous. Six Old
Church Slavonic characters are drawn in their early forms, which modern fonts don't use
(early И looks like H, Н like N, Л like Λ), or can't be identified with confidence. Label
noise would distort the evaluation more than losing these few characters.

## D16. Writer-held-out test split and zero-shot characters (M3, 2026-09-27)

**Decision.**
- 20% of writers go to the test split, chosen by a hash of `dataset:writer`.
- 25% of the characters with real data are zero-shot, chosen by a hash of the code point.
- Training uses only train-split writers of non-zero-shot characters.
- Result: 39,943 test samples, of which 10,779 are of the 244 zero-shot characters.

Hashing makes each assignment independent of file order and stable when data is added.

**Writer ids.**
- Omniglot: the drawer number within an alphabet. We assume it identifies one person per
  alphabet. The dataset doesn't document this. If it doesn't hold, the split is still by
  drawing, never mixing a drawing into both sides.
- UJI: its writer id.
- Detexify has no user ids. The UTC day of a sample's first timestamp is used as a
  pseudo-writer, so a drawing session (usually minutes) stays on one side. A user who
  came back on another day could appear in both splits, which makes the Detexify test
  numbers slightly optimistic.

## D17. Confusable groups: candidates from Unicode, membership from our glyphs (M3, 2026-09-27)

**Decision.** Candidate pairs come from `confusables.txt` (same skeleton), `intentional.txt`
and simple case pairs, 15,402 in total. Case pairs matter because size normalization makes
c/C, o/O, s/S, v/V, w/W, x/X and z/Z identical, and `confusables.txt` doesn't list them.

Two characters share a group only if their glyphs look alike. The measure is the median,
over fonts that have both, of the tolerant overlap of 32×32 ink masks (the share of each
glyph's ink within one pixel of the other's). Groups come from complete-linkage clustering
seeded by the candidate pairs at threshold 0.85, so every two members are at least that
similar.

Result: 834 groups covering 2,284 characters, the largest with 20 members (O o Ο ο О о and
bold/sans variants). Groups are listed in `docs/reports/confusable_groups.md`.

**Why not `confusables.txt` as is.** It puts 𝔄 and 𝒜 with A. Taking the most similar font
instead of the median made 1 ≈ l, because one font draws them alike. Connected components
instead of complete linkage chained 6 – б – о – O and produced an 80-member group of every
vertical stroke.

**Use.** The confusable-aware metrics (M3), negative masking in training (M6) and the
result tiles (M7).

## D18. Drawing rasterization (M3, 2026-09-27)

**Decision.** `glyphsketch.strokes.rasterize` frames a drawing like a glyph: the bounding box
is scaled to 7/8 of the image, keeping the aspect ratio, and centered. It then draws the
strokes as anti-aliased round-capped lines with a distance field,
`ink = clamp(r + 0.5 − d, 0, 1)`. The default pen width is 2.5 px at 64 px. Strokes are
first simplified with Ramer–Douglas–Peucker at a 0.25 px tolerance. A tap becomes a
centered dot.

**Why.** Using the same framing as the glyph renders (D11) means one encoder sees both. The
distance-field formula is simple enough to reproduce exactly in TypeScript and Kotlin, so
the engines' parity tests (M8, M9, M11) can compare images pixel by pixel.

## D19. Evaluation metrics (M3, 2026-09-27)

**Decision.** `glyphsketch.evaluation` scores each test sample on top-1 and top-5, each plain
and confusable-aware (any member of the label's group counts). It reports per sample and
per character (macro), and breaks results down by dataset, Unicode block, and seen versus
zero-shot characters. The macro figure matters because ∫, ∑ and α alone have thousands of
Detexify samples each.

## D20. Trivial baselines: nearest glyph render by pixels or HOG (M4, 2026-09-27)

**Decision.** Two training-free recognizers compare a drawing with all 74,085 glyph renders
and score each character by its best-matching render (cosine similarity):
- **raw pixels:** 32×32 images, Gaussian blur σ = 1 px, mean-centered;
- **HOG:** 64×64 images, 9 unsigned orientations, 8 px cells, 2×2-cell blocks, L2-Hys.

Drawings are rasterized with a pen 7% of the image wide, closer to font stroke weights than
the encoder's default. HOG is our own batched NumPy implementation. It matches
scikit-image's `hog` exactly (cosine 1.0) and is 3× faster, since scikit-image needs
6.9 ms per image.

**Results on the 39,943 test drawings** (full tables in EVAL.md):

| Baseline | Top-1 | Top-5 | Top-1 (conf.) | Top-5 (conf.) |
|----------|------:|------:|--------------:|--------------:|
| Raw pixels | 19.5 | 36.3 | 24.0 | 40.3 |
| HOG | 24.7 | 47.7 | 29.9 | 51.5 |

Chance is below 0.1% with 6,161 candidates. The baselines do worst where the glyph and
the drawing differ most: Mathematical Alphanumeric Symbols (HOG top-5 under 25%, since
drawn 𝒜 and 𝔄 look nothing like the ornate font glyphs), Greek, and UJI's Latin letters.
These are the gaps the encoder has to close.

**Why these two.** They set a floor for M6 and show how much of the task plain template
matching already solves. Zero-shot and seen characters score the same, as expected for
methods without training.
