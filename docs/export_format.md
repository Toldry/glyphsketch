# Export format (version 1)

This is the contract between the training pipeline and the inference engines (TypeScript in
`web/`, Kotlin in `android/`). The `export` stage writes the files to `export/`. The Python
reference is `training/src/glyphsketch/export/` (`ops.run_numpy`, `formats.py`) together
with `strokes.rasterize` and `ranking.Ranker`. An engine is correct when it reproduces
`export/fixtures.json`.

All binary data is little-endian. Every float32 array starts at a multiple of 4 bytes from
the start of its file.

## Pipeline of one query

1. **Rasterize** the strokes into a 64×64 image (see below).
2. **Encode** the image: run the operations in `glyphsketch-model.bin` on a
   (1, 64, 64) float tensor, with ink = pixel / 255. The result is a unit vector of
   `embedding_dim` floats.
3. **Score** every character: the similarity is the largest dot product between the
   embedding and the character's index vectors.
4. **Rank**: `score = similarity + prior_weight · log_prior`, with both values from
   `glyphsketch-charset.json`. Sort by score, highest first.
5. **Tile**: walk the ranked characters and start a new tile at each character whose
   confusable group has no tile yet. Choose each tile's representative as described
   under "Tiles".

## Rasterization

Input: strokes, each a list of (x, y) points (x to the right, y down, any unit). A
stroke with a single point is a tap and is drawn as a dot.

1. Take the bounding box of all points: `min_x, min_y, max_x, max_y`, and let `extent`
   be the larger of `max_x − min_x` and `max_y − min_y`.
   `scale = content_fraction · 64 / extent` (use 1 if `extent` is 0). Map each point
   to `(p − centre) · scale + 32`, where `centre` is the middle of the bounding box.
2. Simplify each stroke with Ramer–Douglas–Peucker at `simplify_tolerance_pixels`
   (0.25), keeping both end points. The reference implementation is iterative and
   splits at the first index of maximal distance, which is its tie rule.
3. Segments: consecutive point pairs of each stroke; a single-point stroke is one
   zero-length segment.
4. For every pixel (centre at `(column + 0.5, row + 0.5)`), take `d`, the distance to the
   nearest segment, clamping the projection to the segment. With
   `radius = pen_width_fraction · 64 / 2`, ink is `clamp(radius + 0.5 − d, 0, 1)`.
5. Store `round(ink · 255)` as a byte (round half to even, as NumPy does; the
   difference only matters at exact halves). Compute in double precision.

`content_fraction` (0.875), `pen_width_fraction` (2.5 / 64) and the tolerance are in
`glyphsketch-charset.json` under `rasterization`.

## `glyphsketch-model.bin`

| Offset | Type | Field |
|-------:|------|-------|
| 0 | 4 bytes | magic `GSKM` |
| 4 | u16 | format version (1) |
| 6 | u16 | input size (64) |
| 8 | u16 | embedding dimensions |
| 10 | u16 | operation count |
| 12 | … | operations, in order |

Each operation starts with a u8 kind:

| Kind | Operation | Body after the kind byte |
|-----:|-----------|--------------------------|
| 1 | Conv | u16 in channels, u16 out channels, u8 kernel, u8 stride, u16 groups, u8 ReLU6 flag; pad to 4 bytes; int8 weights; pad to 4 bytes; f32 scales[out]; f32 bias[out] |
| 2 | Residual begin | none |
| 3 | Residual add | none |
| 4 | Global average pool | none |
| 5 | Linear | u16 in features, u16 out features; pad to 4 bytes; int8 weights; pad to 4 bytes; f32 scales[out]; f32 bias[out] |
| 6 | L2 normalize | none |

Semantics:

- **Weights** are stored in PyTorch order: Conv `[out][in / groups][ky][kx]`, Linear
  `[out][in]`. The real weight is `int8 · scale[out]`: symmetric per-output-channel
  quantization. Engines compute in float32.
- **Conv** uses "same" padding of `kernel / 2` zeros on each side, and the output size is
  `ceil(input / stride)`. `groups` is 1 (dense) or equal to both channel counts
  (depthwise). The bias is added, then `min(max(x, 0), 6)` if the ReLU6 flag is set.
- **Residual begin** pushes the current tensor on a stack; **residual add** pops it and
  adds it element-wise.
- **Global average pool** averages each channel over height and width, which gives a
  vector. **Linear** computes `W · x + b`. **L2 normalize** divides by the Euclidean norm.

## `glyphsketch-index.bin`

| Offset | Type | Field |
|-------:|------|-------|
| 0 | 4 bytes | magic `GSKI` |
| 4 | u16 | format version (1) |
| 6 | u16 | dimensions `D` |
| 8 | u32 | characters `C` |
| 12 | u32 | vectors `V` |
| 16 | u32[C] | code points, ascending |
| … | u32[C] | first vector of each character; character `k` owns vectors `start[k]` up to `start[k + 1]` (or `V`) |
| … | f32[V] | vector scales |
| … | int8[V × D] | vectors, row-major |

A vector is `int8 · scale`, close to unit length. A character has one vector per font that
renders it.

## `glyphsketch-charset.json`

- `characters`: one row per index character, with the columns in `columns`:
  `code_point`, `name`, `block`, `script` (UCD script name, `Common` for symbols),
  `general_category` (UCD, e.g. `Lu`, `Nd`, `Sm`), `group` (the confusable group's smallest code point; the code point itself for a
  character without look-alikes) and `log_prior`.
- `ranking.prior_weight`: the weight of the log prior.
- `keyboard_scripts`: language code → the scripts a keyboard in that language types.
- `rasterization`: the constants above. `input_size`, `embedding_dim`,
  `unicode_version` and `attribution` (show it in the app's about screen) complete it.

## Tiles

For a keyboard language, look up its scripts (default `["Latin"]`). Order a group's
members by:

1. members the keyboard types first: script in the keyboard's scripts, or script `Common`
   or `Inherited` with a general category that is not a letter (`L…`). Digits,
   punctuation and symbols are on every keyboard; styled letters such as 𝐚 are not;
2. higher `log_prior` first;
3. lower code point first.

The first member is the tile's representative. All members, in this order, go in the
tile's chooser. The tile's score is the score of its group's best-ranked member.

## `fixtures.json`

Each case holds the `strokes`, the expected `image_uint8_base64` (64 × 64 bytes,
row-major), the `embedding`, the ten `top_characters` with their `top_scores`, and the
first five `tiles` for a Latin and a Greek keyboard. Tolerances: ±1 per pixel, ±1e-4 for
embeddings and scores. Characters whose scores differ by less than 1e-4 may swap places.
