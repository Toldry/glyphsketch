# glyphsketch: plan

Status: **approved 2026-09-27**, including every change to the approach in section 1.
Only the devcontainer (part of M0) has been implemented. Keep this file current as milestones
complete.

## 1. Changes to the approach

I'd keep **retrieval over font glyphs** as the core idea. It's the only way to meet the
requirement that a new character needs no new handwriting data. I'd change or add the
following:

1. **Rasterize the drawing and ignore stroke order.** Font glyphs have no stroke order or
   direction, so a stroke-sequence model can't be applied to the glyph side of the index.
   A raster encoder with one set of weights shared by both sides is the simplest design
   that keeps the index consistent with the model.
2. **Try two ways of building the index.** Option (a) embeds the clean glyphs. Option (b)
   embeds K synthetic hand-drawn renderings per glyph and font and averages them into one
   "prototype" vector. Option (b) costs only more work at export time and may close much
   of the gap between handwriting and font rendering. The evaluation decides which one
   ships.
3. **Don't use confusable pairs as negatives.** If Latin `A` and Greek `Α` are treated as
   negatives, the loss pushes apart two images that are pixel-identical. Negatives are
   masked by confusable group. Hard negatives are mined across different groups only.
4. **Add a zero-shot evaluation split.** The main claim is that the model generalizes to
   characters with no real handwriting in training. EVAL.md will report the characters
   with real data separately from the characters seen only as synthetic data during
   training.
5. **Use pure inference engines with a shared weight format.** Engines are written in
   TypeScript now and Kotlin at the end. ONNX is kept as an export for reference and
   benchmarking. My expectation, to be confirmed in M11: ONNX Runtime ships native `.so`
   files for each ABI, F-Droid wants everything built from source, and Thumb-Key has no
   native dependencies today. A CNN of about 1M parameters at 64×64 needs roughly
   20–60 MFLOPs, which a plain engine can run well under 50 ms.
6. **Web first.** During development the web demo is the test bench for drawing by hand.
   It also collects labelled drawings locally, which you can export for a personal
   sanity-check set. Android comes last.

## 2. Milestones

Each milestone ends with tests passing, an entry in DECISIONS.md and focused commits.

| # | Milestone | Exit criteria |
|---|-----------|---------------|
| M0 | **Devcontainer + skeleton** (devcontainer done) | Container builds; `LICENSE` (AGPL-3.0), `THIRD_PARTY.md`, `DECISIONS.md`, directory layout, GitHub Actions CI (Python tests + lint) |
| M1 | **Charset builder** | UCD pinned to the latest release. Exclude Cn/Co/Cc/Cf/Zs/Zl/Zp/Cs and combining marks (Mn/Me). v0 block list. Keep only emoji-presentation characters that have a text-presentation glyph in a free font. `charset.json` with code point, name, block, script, general category. Tests |
| M2 | **Fonts + renderer** | Pinned font downloads with checksums. fontTools cmap check (never `.notdef` or fallback). Several fonts per character. Coverage report per block. Tests |
| M3 | **Real data + eval harness** | Detexify loader with a LaTeX→Unicode mapping. Omniglot alphabets in scope hand-mapped to code points, with the mapping in the repo. Held-out test split by writer. Top-1/top-5 metrics per block, plain and confusable-aware. Tests |
| M4 | **Trivial baselines** | Raw-pixel and HOG nearest neighbour against the glyph renders. First EVAL.md numbers |
| M5 | **Synthetic handwriting generator** | Skeletonize, extract strokes, pen trajectories, variable width, elastic/affine jitter. Visual gallery. Tests. Deterministic from a seed |
| M6 | **Contrastive encoder** | Small CNN, 128-d L2-normalized output, InfoNCE with confusable-masked hard negatives. Ablations: synthetic-only vs. synthetic + real, and index option (a) vs. (b). Zero-shot split reported |
| M7 | **Ranking + homoglyphs** | Score = similarity + λ·log(prior). Prior computed from Wikipedia dump character counts, source and dump date documented. Confusable groups from `confusables.txt`. Result-tile design: one tile per group, script chosen from the keyboard language |
| M8 | **Export** | int8 per-channel quantization. Compact binary weights, int8 index, charset metadata, ONNX reference. Parity fixtures (input → expected output) for the engines. Size ≤ 10 MB |
| M9 | **Web library + demo** | TypeScript engine with parity tests. Canvas demo (Vite) that shows candidates, per-query latency, and a local labelled-drawing export |
| M10 | **EVAL.md + Detypify comparison** | Full report. Comparison with Detypify on its symbol set, with a warning about possible overlap with Detexify training data |
| M11 | **Android library + demo (last)** | Pure-Kotlin engine with unit tests against the parity fixtures. ONNX Runtime benchmarked on the Pixel 8 (over Wi-Fi `adb`). Written recommendation. Compose demo. minSdk 24 (matches Thumb-Key) |
| M12 | **Later, to be decided** | Combining marks (e.g. drawn on a dotted circle ◌́). CJK as an optional index pack |

`training/` runs end to end with one command (`uv run python -m glyphsketch.pipeline all`,
or a `make all` wrapper). Each stage caches its output in `$DATA_DIR`.

**Budget estimate:** A v0 charset of about 8–12k code points (to be measured in M1) at 128-d
int8 makes an index of about 1–1.5 MB. The model is about 0.3–1 MB in int8. Metadata is
under 1 MB. **CJK later:** about 100k characters at 128-d is about 12.8 MB, over budget.
The index will be sharded by block, so CJK becomes an optional pack, possibly at 64-d or
product-quantized.

## 3. Compute

**Your machine:** ASUS Zenbook Duo UX8406MA (2024), Intel Core Ultra 9 185H (16 cores,
22 threads), 32 GB LPDDR5X, Intel Arc iGPU, Intel AI Boost NPU (about 11 TOPS, inference
only), no NVIDIA GPU.

- **Inside the container, training is CPU-only.** Docker Desktop passes only NVIDIA GPUs
  through to containers. My rough estimate is on the order of 1k samples/s, so about
  20–30 min per million-sample epoch. That's fine for baselines, debugging and short runs.
- **Arc GPU on the Windows host:** PyTorch's XPU backend supports Arc, but it runs outside
  the sandbox. Treat it as optional.
- **Cloud, free or cheap (check current terms and prices):**
  - **Kaggle Notebooks:** free, about 30 GPU-hours/week (T4×2 or P100). My first choice.
  - **Google Colab (free tier):** a T4 when available. Sessions get cut off.
  - **Lightning AI / Modal:** small monthly free credits and scriptable jobs.
  - **Vast.ai / RunPod:** rented RTX 3090/4090 at roughly $0.2–0.5/h.

## 4. Decisions made

- Hosting: GitHub. Repository name: `glyphsketch` (free on GitHub, npm, PyPI, Maven
  Central and F-Droid as of 2026-09-27).
- ODbL (Detexify): the trained model is treated as a Produced Work and gets an
  attribution notice. The data is never redistributed. No legal review.
- Omniglot: hand-map the alphabets that are in scope.
- Combining marks: excluded from v0 and moved to M12.
- Emoji: keep only characters that have a text-presentation glyph in a free font.
- Frequency prior: Wikipedia dump character counts.
- Unicode version: pin the latest released UCD in M1.
- Android: last milestone. Web is the development test bench.
