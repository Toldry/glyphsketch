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
- CJK: planned as an optional index pack (M12). Superseded: CJK is excluded (D35).

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

## D21. Synthetic handwriting from glyph skeletons (M5, 2026-09-27)

**Decision.** Synthetic drawings are made in stroke space, not pixel space:

1. **Strokes from glyphs** (`synth/skeleton.py`, run once by the `glyphstrokes` stage for
   all 74,085 renders, median 3 strokes each).
   - Each render is skeletonized and the skeleton traced as a graph. Junction pixel
     clusters form single nodes, and diagonal shortcuts past an orthogonal neighbour are
     ignored.
   - Spurs shorter than 9% of the glyph are pruned. All spurs at a junction go at once, as
     long as a longer branch remains there.
   - Branches are joined through corners, and through junctions where they continue
     within 50°. A T becomes a bar and a stem, an A an inverted V and a bar.
   - Two special cases. Large filled shapes (■ ● ★ ♥ ⬅) use their outline contours, since
     people draw outlines and a skeleton would give spokes. Small blobs (. · •) become a
     single point, since people tap them.
2. **Distortion** (`synth/augment.py`, in normalized coordinates, all amounts relative to
   the drawing size):
   - closed loops are cut open at a random point 60% of the time;
   - per-stroke shift ±2.5%, rotation ±5° and scale ±8%;
   - end points extended or trimmed by up to 4%, leaving the gaps and overlaps real
     drawings have;
   - perpendicular wobble up to 0.8%;
   - corner rounding (Gaussian, σ up to 2.5%);
   - a 3-component low-frequency elastic field (amplitude 3.5%);
   - global rotation ±9°, shear ±0.22 and aspect ±25%;
   - pen width 1.4–4.2 px at 64 px (log-uniform).
3. **Rasterization** with the same rasterizer and framing as real input (D18).
4. **Font choice by style.** For each character a render is picked with weights
   handwriting 3, sans 2, symbols 1.5, serif/mono/math 1. Serif skeletons keep their
   serifs as short strokes (they are as long as real parts of other glyphs, so no
   threshold removes them safely), so serif fonts are sampled less often.

**Determinism.** Each sample is fully determined by (seed, code point, sample index), which
seed a NumPy generator. The training data uses seed 1. Index prototypes (option (b)) use
sample indices from 1,000,003 on, so they never coincide with training samples.

**Checks.** `docs/images/synthetic_gallery.png` shows, per character, a glyph, ten
synthetic drawings and five real drawings. Letters, digits, Greek, math operators,
Cyrillic, Hebrew, Arabic, symbols and filled shapes look like the real ones. The visible
gap is ornate styles: synthetic 𝒜 keeps the script font's flourishes, while people draw a
plain A with a curl. Real training data (M6) is the way to close it.

**Alternatives.** Distorting the rendered glyph image directly (elastic warps plus
thickness changes) can't separate strokes, so it can't move them independently or
misjoin them. A learned model of handwriting would need handwriting for every
character, which is exactly what the design avoids.

## D22. Encoder, loss and batches (M6, 2026-09-27)

**Encoder.** A MobileNetV2-style CNN on 64×64 images: a 3×3 stride-2 stem (16 channels),
seven inverted residual blocks (24 → 48 → 96 → 192 channels, three stride-2 steps), a
1×1 head to 384 channels, global average pooling and a linear layer to 128 dimensions,
L2-normalized. It costs 22.4M multiply-adds and has 546k parameters, about 0.55 MB in
int8. It uses only 3×3 (standard and depthwise) and 1×1 convolutions, batch norm (folded
at export), ReLU6, average pooling and one linear layer, so the TypeScript and Kotlin
engines stay small. Drawings and glyphs share the same weights.

**Loss.** Each batch holds B = 256 distinct characters, each with two drawing views and
one glyph render. Three InfoNCE terms with a learned temperature: drawing → glyph and
glyph → drawing (what index option (a) needs), and drawing → other drawing (what index
option (b), averaged drawing prototypes, needs). Pairs of distinct characters in the same
confusable group are masked out of the softmax, so pixel-identical characters (A, Α, А)
are never pushed apart.

**Hard negatives.** Half of each batch comes from neighbourhoods: a seed character plus up
to 7 of its 24 nearest characters from other confusable groups. The neighbours start from
HOG similarity of the glyph renders and are recomputed every 500 steps from the model's
own glyph embeddings.

**Data.** The `encoderdata` stage pre-generates 96 synthetic drawings per character
(591,456 images, seed 1), the 64 px glyph renders (74,085), and the real training and test
drawings rasterized like real input (132,974 and 39,943). In the synthetic-and-real
experiment, each view is a real drawing with probability 0.35 when the character has
real training drawings. Zero-shot characters and test-split writers are never used in
training.

**Alternatives.** A triplet loss uses one negative per anchor where InfoNCE uses the whole
batch, and it needs careful margin tuning. A classifier with a softmax over characters
would tie the model to a fixed character set, which the design rules out.

## D23. Training on the laptop CPU (M6, 2026-09-27)

**Threads.** Every worker pool starts single-threaded workers (OpenBLAS, OpenMP and MKL
set to one thread) and uses half the cores by default (`GLYPHSKETCH_WORKERS` overrides);
training uses the same number of torch threads. Before this, 20 workers each started a
thread per core (about 40 each) and made the laptop unusable. `make slowdown` pauses,
postpones or stops heavy jobs if the laptop still gets slow.

**Speed.** Channels-last memory layout makes a training step 1.8× faster on this CPU
(3.3 → 1.9 s for 768 images). Batch assembly takes 3 ms; the model is the bottleneck, as
expected for depthwise convolutions on a CPU. At about 450 images/s, a 40-minute run gets
about 1,400 steps, roughly one pass over the synthetic pool.

**Time budget.** With a wall-clock budget, the cosine decay follows whichever of steps and
time runs out first. A run cut short by time still ends with a low learning rate, instead
of saving a checkpoint from the middle of the schedule.

**Consequence.** CPU runs are short and serve the ablations. The final encoder is trained
on a Kaggle GPU (D24).

**Equal steps, not equal time.** The laptop's speed varies a lot: after about 1.5 hours of
load, the same benchmark ran 5× slower (a single-threaded Python loop too, with nothing
else running), most likely Windows power management or heat. A time budget then buys
far fewer steps, so ablations compare runs with the same number of steps. The first run
sets the number (synthetic-only: 1,701 steps in 40 minutes), and later runs use
`--steps` with the time budget only as a safety cap.

## D24. Long runs on Kaggle (M6, 2026-09-27)

`uv run python -m glyphsketch.tools.kaggle_bundle` writes one zip with the package
source and the stage files the experiments read (about 500 MB compressed, mostly the
pre-generated images), with a SHA-256 manifest and the git commit.
`training/kaggle/glyphsketch_train.ipynb` finds it under `/kaggle/input`, links it into
`$DATA_DIR`, runs each entry of its `RUNS` list with `glyphsketch.model.experiments` on the
GPU as a subprocess, and writes one results zip laid out like `$DATA_DIR` (checkpoints,
training logs, evaluation reports). The default list is the equal-step ablation pair
(1,701 steps each) and a long run of each variant (30,000 steps, capped at 200 minutes
each). A dry run from the unpacked bundle, with the input read-only and only the bundled
code on the path, trained, evaluated and wrote all outputs.
Unpacking that zip into `/data` makes EVAL.md pick the results up.

The bundle holds data derived from Detexify (ODbL) and font renders, so the Kaggle dataset
must stay private: it is a working copy for training, not a redistribution.

**Alternatives.** Regenerating the images on Kaggle would upload only about 130 MB, but
Kaggle's 4 CPUs and different library versions would give different training data from
the CPU ablations. Installing the package with pip would enforce `requires-python >= 3.12`,
which Kaggle's image may not meet; the source is checked to compile on Python 3.11 and
is put on `PYTHONPATH` instead.

## D25. Character-frequency prior from sampled Wikipedia dumps (M7, 2026-09-27)

**Source.** The pages-articles-multistream dumps of 2026-09-01 for 18 languages that cover
the charset's scripts: Latin (en, de, fr, es, it, pt, pl, cs, tr, vi), Cyrillic (ru, uk,
bg, sr), Greek (el), Hebrew (he) and Arabic (ar, fa). The settings live in
`resources/wikipedia_prior.toml`.

**Sampling.** A multistream dump is a concatenation of independent bz2 streams of 100
pages, so a byte range can be cut to the complete streams inside it. Per language, 24
ranges of 4 MiB are fetched at evenly spaced points over the whole dump (over all parts
when it is split): 1.7 GB in total instead of 72 GB for the full dumps, and 12
minutes on the laptop. The sample holds about 870,000 articles and 3.1 billion characters.
The ranges and a SHA-256 per chunk are recorded in the stage output.

**Counting.** Articles only (namespace 0, no redirects). Wikitext is cleaned by rules, not
parsed (`prior/wikitext.py`): comments, code-like blocks, URLs, tags, link and template
brackets, template parameter names and table syntax go; their text stays. Maths is
LaTeX inside `<math>`, so its commands are mapped to code points with the reviewed
Detexify mapping, 16 common aliases (`\le`, `\to`, …) and the styled alphabets
(`\mathbb{R}` → ℝ). Without that, ∫ or ≤ would hardly occur.

**Combination.** Per language, the frequency over the charset's characters, with an
add-½ count for every character; then the plain mean over languages. A script used by
few languages (Hebrew) still gets its characters' weight from those languages, and the
3,811 characters that occur in the sample outrank the 2,350 that don't. The value
shipped is the natural log (from −2.9 for e down to −19.6).

**Alternatives.** A single English dump would make every non-Latin character rare.
Weighting by speakers or by wiki size would do the same for Greek or Hebrew. Published
frequency tables exist only per language and seldom cover symbols. Full dumps would cost
40× the download for estimates that are already stable: the smallest counted language has
131 million characters.

## D26. Ranking and result tiles (M7, 2026-09-27)

**Score.** `similarity + weight · log prior`, with the similarity of index option (a)
(best match over the character's renders). The weight is tuned on 20,000 real drawings
from the training split that a synthetic-only encoder never saw; the test set is never
used for tuning. Encoders trained on real drawings reuse the weight tuned on a
synthetic-only encoder. On the laptop's synthetic-only encoder the best weight is 0.002.
It raises top-1 from 41.3% to 47.3% and top-5 from 71.9% to 76.1% on the test set. The
optimum is sharp: at 0.01 the gain is gone, and at 0.02 the prior dominates. So the
grid is fine around it.

**Tiles.** Members of a confusable group can't be told apart once drawn, so results show
one tile per group, in the order of the group's best score. The tile shows the most
frequent member that the keyboard types: a letter of the keyboard language's script (from
`resources/wikipedia_prior.toml`; a keyboard for Greek shows Α, one for English shows A),
or a digit, punctuation mark or symbol (script Common, not a letter), which every
keyboard types. Without such a member it shows the most frequent member. Both parts of
the rule came from the fixtures: preferring only the keyboard's script showed ɜ for a
drawn 3 and Ʃ for ∑ on an English keyboard, and counting every Common character as typed
let styled letters (𝐚, 𝛌) through. The other members are offered on the tile (a
long press in Thumb-Key, a small menu in the web demo). Tiles raise the confusable-aware
top-5 to 81.3%, because merged look-alikes free slots for other candidates.

**Evaluation of tiles.** The test set has no keyboard language, so the evaluation assumes
one in the drawn character's script (Latin for symbols). Exact top-1 of tiles then
measures the representative choice. It is 1.5 points below ranked characters because case
pairs share a group once size is normalized: a drawn O shows the more frequent o, and O is
in the tile's menu.

**Alternatives.** A script chooser on every tile would cost a tap for the common case. A
prior per keyboard language would need a table per language (18× the size) for a gain the
script rule already gives inside groups.

## D27. Export: int8 weights, PCA-reduced per-font index, JSON metadata (M8, 2026-09-27)

**Index size.** Index option (a) keeps one vector per glyph render (74,085 vectors), which
wins on accuracy (D22 results) but takes 9.5 MB at 128 dimensions in int8, over the
budget with the model and metadata. Measured on the laptop encoder (test set, prior on):

| Variant | Vectors × dims | int8 size | Top-1 | Top-5 (conf.) |
|---------|---------------:|----------:|------:|--------------:|
| per font, float | 74,085 × 128 | 9.5 MB | 47.3 | 79.1 |
| per font, int8 | 74,085 × 128 | 9.5 MB | 47.3 | 79.2 |
| per font, 4-bit | 74,085 × 128 | 4.7 MB | 46.4 | 78.7 |
| mean per character | 6,161 × 128 | 0.8 MB | 42.9 | 74.5 |
| greedy dedupe at cosine 0.90 | 10,889 × 128 | 1.4 MB | 39.1 | 74.7 |
| k-means, 4 per character | 22,883 × 128 | 2.9 MB | 44.8 | 77.2 |
| PCA to 48 dimensions | 74,085 × 48 | 3.6 MB | 47.2 | 79.1 |

The embedding uses few of its 128 dimensions (46 hold 99% of the variance), so a PCA
projection loses nothing, while every way of dropping vectors does. The projection is
fitted on the index vectors and folded into the encoder's last linear layer, so it costs
nothing at inference. Its size is chosen at export as the smallest of 32, 48, 64 or 96
dimensions within 0.2 points of the full embedding on the 20,000 validation drawings
(confusable-aware top-1 and top-5); here 48. The test set plays no part in the choice.

**Model.** Batch norm is folded into the convolutions; weights are symmetric int8 per
output channel with float32 scales and biases (541 kB). Engines dequantize at load and
compute in float32: int8 is for size, and float arithmetic keeps the engines simple and
their results equal to the reference. Integer arithmetic is an option for M11 if the
Pixel 8 needs it.

**Formats.** Small custom binaries (`GSKM`, `GSKI`) instead of ONNX or FlatBuffers: a
TypeScript or Kotlin reader is about 100 lines with no dependencies, which matters for
F-Droid. The operation list has seven kinds (`docs/export_format.md`). Metadata is JSON
(575 kB, 79 kB gzipped), since both platforms parse it natively. The ONNX file is
a reference for benchmarking ONNX Runtime in M11 and is not shipped: it matches the int8
network to 2e-7.

**Checks.** The export evaluates its own files, read back, on the test set: 47.2% top-1
and 79.1% top-5 confusable-aware ranked, 81.2% tile top-5; the same as the float model.
The shipped files total 5.02 MB. `export/fixtures.json` holds 25 synthetic drawings
(fonts only, no dataset samples) with the expected input image, embedding, ranking and
tiles for a Latin and a Greek keyboard. They exposed two flaws in the first tile rule
(D26).

**Not yet committed.** The files in `export/` come from the laptop's short run. They are
committed with the final encoder from Kaggle, so the repository doesn't collect 5 MB per
intermediate model.

## D28. TypeScript engine and demo without a bundler (M9, 2026-09-27)

**Engine.** `web/src/` implements `docs/export_format.md` with no runtime dependencies:
the rasterizer (double precision, then NumPy's float32 multiply and round-half-to-even,
so images match byte for byte), the model reader and forward pass (float32, weights
dequantized at load), index scoring, ranking and tiles. All 25 export fixtures pass:
images identical, embeddings and scores within 1e-4, identical top-10 and tiles.

**Speed.** In Node 24 on the laptop, a query takes 20 ms (median; 28 ms p95): 0.7 ms to
rasterize, 13 ms to encode, 6 ms to score 74,085 index vectors and rank. The first
version took 42 ms, 32 ms of it in 1×1 convolutions. Blocking those as 4 outputs × 4
inputs, so each loaded value feeds four accumulators, cut them to 9 ms. Depthwise
convolutions skip bounds checks for interior pixels, and a query ranks once instead of
twice.

**Tooling: no Vite, no test framework.** PLAN.md named Vite for the demo. The demo is one
static page, and modern browsers load ES modules directly, so `tsc` output is enough.
Tests use Node's built-in runner, which runs TypeScript directly now that Node strips
types. The only dev dependencies are the TypeScript compiler and Node's type definitions
(23 locked packages, 20 of them per-platform compiler binaries), instead of the dozens
that Vite and Vitest pull in, each of which THIRD_PARTY.md would have to record.
`web/scripts/serve.ts` is a 50-line static server restricted to `web/` and `export/`.

**Demo.** `web/demo/` shows five tiles (tap to type, long-press or right-click for the
look-alikes), the ten ranked candidates with names and scores, the timings and the 64×64
input image. A keyboard selector covers the 18 prior languages. Labelled drawings are
saved to local storage and exported as JSON for a personal test set (PLAN.md, section 1,
change 6). The page was checked through its server with curl. A headless browser needs
system libraries the container lacks (it has no root), so the interaction was not
tested automatically; the engine under it is.

## D29. M6 results and the shipped encoder (M6–M8, 2026-09-28)

Kaggle (T4) ran the equal-step ablation pair (1,701 steps, 9 minutes each) and a long run
of each variant (30,000 steps, 163 minutes each). Test set, index (a) per font, no prior:

| Run | Top-1 | Top-5 | Top-5 (conf.) | Top-5 (conf.), zero-shot |
|-----|------:|------:|--------------:|-------------------------:|
| synthetic only, 1,701 steps | 40.6 | 71.5 | 76.4 | 72.8 |
| synthetic + real, 1,701 steps | 43.5 | 74.8 | 79.2 | 75.0 |
| synthetic only, 30,000 steps | 42.4 | 72.9 | 77.4 | 74.9 |
| synthetic + real, 30,000 steps | 49.7 | 82.4 | 86.0 | 78.4 |

- **Real drawings help, including zero-shot characters**, which have no real drawings:
  zero-shot top-5 (conf.) rises from 74.9 to 78.4 in the long runs. Real handwriting
  teaches the encoder how people draw in general (proportions, sloppy joins), not just
  the characters in the data.
- **Synthetic-only training plateaus:** 17× the steps gains 1 point. The gap between
  synthetic and real drawings, not training time, limits it.
- **Index (a) per font wins in every run**, ahead of (a) mean by 2–5 points and (b)
  synthetic prototypes by 4–5. Prototypes average away the styles people draw.

**Shipped:** synthetic + real, 30,000 steps, index (a) per font, prior weight 0.002 (tuned
on validation drawings with the long synthetic-only encoder, for which they are unseen;
the same value as on the laptop's encoder). The export's validation check chose 48
dimensions; for this encoder the validation drawings are training data, so that check
is optimistic, but the test set agrees: the exported int8 package scores as the float
model. Test set: 53.4% top-1 and 86.8% top-5 (conf.) ranked; tiles 56.9% exact top-1 and
89.9% top-5 (conf.), 85.0% on zero-shot characters. 5.02 MB shipped.

**Caveat.** The test set is 93% Detexify (maths symbols drawn in its web app), so these
numbers describe that mix. The per-block tables in EVAL.md and the web demo's labelled
drawings are the check for other use.

## D30. The web demo on GitHub Pages (2026-09-28)

The demo is served by GitHub Pages from a `gh-pages` branch. The `Pages` workflow runs on
pushes to `main` that touch `web/` or `export/`: it runs the web tests (so a deploy never
breaks parity), builds the site with `web/scripts/build_site.ts`, and force-pushes it as
one orphan commit. Keeping one commit stops the 5 MB of exported files from piling up in
the branch's history.

The site mirrors the repository layout (`web/demo/`, `web/dist/`, `export/`) so the
demo's relative paths work unchanged, with a redirect at the root. It publishes only the
shipped files: the ONNX reference and fixtures stay out. A hosted AGPL program must offer
its source to users, so the build writes `source.json` (repository and commit), and the
page links the exact commit in its footer.

**Alternative.** GitHub's "Actions" Pages source (upload-pages-artifact and deploy-pages)
needs no branch, but the user asked for a `gh-pages` branch, and a branch can be
inspected and rolled back with plain git.

## D31. EVAL.md as a written report, and the Detypify comparison (M10, 2026-09-28)

EVAL.md stays generated (`evalreport` stage), so its numbers can't drift from the saved
reports. It now opens with the shipped package's results, the Detypify comparison, the
strongest and weakest Unicode blocks and the limitations, and keeps every run's full
tables in collapsed sections below.

**Detypify** (MIT, pinned npm package 0.3.0: its ONNX model and 411-symbol list) runs on
the test drawings of its symbols. Its preprocessing is reproduced from `drawStrokes`,
drawn with our rasterizer rather than a browser canvas. Detypify takes one image per call
at 224×224, about 0.17 s per drawing on the laptop, so the comparison uses a fixed
random sample of 6,000 of the 29,255 eligible drawings (standard error about 0.6
points); the full set would take about 3 hours.

Result: on its own symbols Detypify is ahead (top-1 87.8% against glyphsketch's 76.8%
with the same 411 candidates, top-5 99.6% against 98.2%). Searching all 6,161
characters, glyphsketch gets 57.9% top-1 and, as tiles, 93.1% top-5 counting look-alikes.
Part of Detypify's lead may be overlap: it trains on Detexify data, and nothing says our
test writers are excluded. A fixed-set classifier trained on real drawings is the better
tool for a fixed symbol set; glyphsketch's design buys coverage (15× the characters,
most without handwriting data) and adding characters from a font alone.

## D32. Latency budget relaxed to 300 ms per query (2026-09-28)

The brief asked for under ~50 ms per query on a mid-range phone. The user relaxed it to
300 ms: waiting 0.3 s for results after finishing a drawing is acceptable. For
reference, the TypeScript engine takes 20 ms per query in Node and 43.5 ms in the user's
browser on the laptop. The phone numbers come in M11. The new budget leaves room for a
larger encoder later if accuracy needs it, and makes the pure-Kotlin engine (no native
code) an easier choice.

## D33. Project logo (2026-09-28)

The logo is the user's "GS" drawn in the web demo (`docs/logo/gs-drawing.json`),
rendered by `glyphsketch.tools.logo` in the drawing pad's dark-theme colours: light
round-capped strokes (#ececf0) on the pad's grey (#222228). `logo.svg` keeps the pad's
pen width; `favicon.svg` (the demo's favicon) doubles it and a half, since at 16–32 px
the pad's width would be under a pixel.

## D34. Extended charset: emoji, combining marks, compatibility forms and more symbols (2026-09-28)

The user asked for everything v0 had left out except CJK. D8 (no emoji font) and the M12
deferral of combining marks are replaced.

**Added blocks** (`resources/charset_v0.toml`): emoji and pictographs (Miscellaneous
Symbols and Pictographs, Emoticons, Transport and Map Symbols, Supplemental Symbols and
Pictographs, Symbols and Pictographs Extended-A); Musical Symbols and its supplement;
Chess, Mahjong, Domino and Playing Cards; Alchemical and Ancient Symbols; Box Drawing,
Block Elements, Braille Patterns and Symbols for Legacy Computing (and supplement);
Geometric Shapes Extended, Supplemental Arrows-C, Ornamental Dingbats, Enclosed
Alphanumeric Supplement, Miscellaneous Symbols Supplement, Miscellaneous Symbols and Arrows
Extended; the combining mark blocks; and the compatibility forms (Alphabetic and Arabic
Presentation Forms, Halfwidth and Fullwidth Forms, Small Form Variants, Vertical Forms).
Combining marks (Mn, Me) are no longer excluded anywhere, so Hebrew points and Arabic
vowel marks come in too. CJK stays out (D35), as do historical music notations and
Yijing symbols.

**Fonts.** Noto Emoji (monochrome outlines; a colour emoji can't be compared with a pen
drawing) and Noto Music, both OFL from the pinned Google Fonts commit. Glyphs at huge
render sizes (a tiny mark scaled to the box) overflowed FreeType's rasterizer; the
renderer now retries at half the size.

**Known limits, accepted.** Many added characters can't be told apart once drawn:
heavy and light box lines, single-dot braille patterns (size normalization makes them one
dot), presentation forms that look like their base letters. The look-alike groups put
those in one tile's menu. Emoji families (😀 😃 😄) differ in details a rough drawing
lacks. Nothing in the real datasets covers the new characters, so they are measured only
by synthetic drawings and the user's labelled drawings.

**Prior.** Emoji barely occur in Wikipedia. Unicode's emoji frequency ranking would fit,
but it is website content whose terms of use forbid incorporating it into a product (only
the files under /Public/ and the like are under the Unicode License). So every
Extended_Pictographic character gets one flat prior (the user's choice): the median log
prior of the characters the sample contains at least 100 times, about the level of ∫, ≤
and € (−13.6). The plain median would be the floor, since most characters occur only a
handful of times.

**Display.** A combining mark is shown after a dotted circle (◌́) in tiles, menus and
candidate lists (`docs/export_format.md`); choosing it inserts the bare mark.

**Compatibility forms and the look-alike groups.** Clustered like other characters, the
fullwidth letters joined both the o and the O cluster early and then blocked the merge
of the two (complete linkage), splitting o/O, c/C and w/W. Compatibility forms
(decomposition tags `<wide>`, `<narrow>`, `<small>`, `<vertical>`, `<isolated>`,
`<initial>`, `<medial>`, `<final>`) now stay out of the clustering and join their base
character's group afterwards if their glyphs are similar enough (`confusables.py`).

**Result, current encoder (no retraining).** 10,776 characters (was 6,161), 89,437
renders, 1,040 confusable groups; 6.30 MB shipped. On the real test set (old characters
only, plus 212 drawings of 3 Detexify symbols whose Unicode characters are new), the
extra candidates cost little: tile top-5 (conf.) 87.5% (was 89.9%), ranked top-1 52.2%
(was 53.4%). On held-out synthetic drawings of the new characters
(`glyphsketch.tools.new_characters`, 5 per character, tiles, Latin keyboard), top-5
(conf.): emoji and pictographs 90.4%, compatibility forms 94.8%, other new symbols 80.7%,
music and games 68.4%, combining marks 68.2%, box, block and braille 65.5%. Synthetic
drawings flatter the recognizer, so read these as a comparison baseline for the retrained
encoder, not as real-world accuracy.

**Retrained encoder (shipped).** The long synthetic+real run was repeated on Kaggle on the
extended charset, with the same settings (`synthetic-and-real-long-v2`, 30,000 steps,
2.9 h). Both encoders scored on the same 10,776-character index, tiles, top-5 (conf.) /
top-1:

| Test drawings | Current encoder | Retrained |
|---|---:|---:|
| Real, characters seen in training | 89.8% / 58.6% | 88.7% / 56.4% |
| Real, zero-shot characters | 81.2% / 46.9% | 80.9% / 48.5% |
| Synthetic: emoji and pictographs | 90.4% | 98.8% |
| Synthetic: compatibility forms | 94.8% | 97.6% |
| Synthetic: other new symbols | 80.7% | 91.1% |
| Synthetic: music and games | 68.4% | 91.8% |
| Synthetic: box, block and braille | 65.5% | 78.0% |
| Synthetic: combining marks | 68.2% | 74.9% |

The retrained encoder is shipped (`export.toml`): on real handwriting it is level for
characters it has not seen and about one point lower for the others (the same model
capacity now covers 75% more characters), and it is far better on the new characters.
It has seen synthetic drawings of those (from another generator seed), as the current
encoder had for the old characters, so the synthetic columns flatter it somewhat more.
Adding a character still needs no handwriting data: the current encoder's column is what
an index-only addition gives.

## D35. CJK stays out (2026-09-29)

The user decided to keep CJK excluded. The optional CJK index pack planned for M12 is
dropped; there is no M12. Excluded are the CJK Unified Ideographs and their extensions,
CJK Compatibility Ideographs, Hangul syllables and Jamo, Kana, Bopomofo, Kangxi and CJK
radicals, and the other East Asian blocks the v0 block list never named
(`resources/charset_v0.toml` lists the blocks to include).

Two listed blocks did contain East Asian characters: Halfwidth and Fullwidth Forms
(halfwidth katakana and Hangul, with no full-width base in the charset) and Spacing
Modifier Letters (two Bopomofo tone letters, ˪ ˫). The config now also excludes by script
(`excluded_scripts`: Han, Hangul, Hiragana, Katakana, Bopomofo, Yi), which drops 109
candidates; 57 of them had font coverage (55 halfwidth katakana and ˪ ˫), so the shipped
charset goes from 10,776 to 10,719 characters. The encoder needs no retraining (the index
just loses those vectors). Fullwidth Latin letters and punctuation stay in, as
compatibility forms (D34).

**Why this is cheap to reverse.** Nothing in the design assumes a fixed charset: a pack
would be a second index over the same encoder, loaded next to the first. The recognizer
would need no handwriting data for it (the brief's key idea), but it would need a CJK
font, a budget decision (about 100k characters, well over 10 MB at 48 int8 dimensions
unless product-quantized), and CJK drawings to test with, since stroke-dense characters
at 64×64 are untested.
