# glyphsketch: plan

Status: **approved 2026-09-27**, including every change to the approach in section 1.
Keep this file current as milestones complete. The Status column of the milestone table
shows where each milestone stands.

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
   20–60 MFLOPs, which a plain engine can run well under 50 ms. (The budget is now 300 ms;
   see D32.)
6. **Web first.** During development the web demo is the test bench for drawing by hand.
   It also collects labelled drawings locally, which you can export for a personal
   sanity-check set. Android comes last.

## 2. Milestones

Each milestone ends with tests passing, an entry in DECISIONS.md and focused commits.

| # | Milestone | Exit criteria | Status |
|---|-----------|---------------|--------|
| M0 | **Devcontainer + skeleton** | Container builds; `LICENSE` (AGPL-3.0), `THIRD_PARTY.md`, `DECISIONS.md`, directory layout, GitHub Actions CI (Python tests + lint) | Done 2026-09-27 (CI runs once a remote exists) |
| M1 | **Charset builder** | UCD pinned to the latest release. Exclude Cn/Co/Cc/Cf/Zs/Zl/Zp/Cs and combining marks (Mn/Me). v0 block list. Keep only emoji-presentation characters that have a text-presentation glyph in a free font. `charset.json` with code point, name, block, script, general category. Tests | Done 2026-09-27: Unicode 18.0.0, 6,454 candidates; the emoji rule is applied by M2's coverage filter (D8) |
| M2 | **Fonts + renderer** | Pinned font downloads with checksums. fontTools cmap check (never `.notdef` or fallback). Several fonts per character. Coverage report per block. Tests | Done 2026-09-27: 48 fonts, 6,161 characters, 74,085 renders; report in `docs/reports/glyph_coverage.md` |
| M3 | **Real data + eval harness** | Detexify loader with a LaTeX→Unicode mapping. Omniglot alphabets in scope hand-mapped to code points, with the mapping in the repo. Held-out test split by writer. Top-1/top-5 metrics per block, plain and confusable-aware. Tests | Done 2026-09-27: Detexify + Omniglot + UJI (223k samples, 998 characters); 834 confusable groups; reports in `docs/reports/` |
| M4 | **Trivial baselines** | Raw-pixel and HOG nearest neighbour against the glyph renders. First EVAL.md numbers | Done 2026-09-27: HOG 24.7% top-1, 47.7% top-5 (51.5% confusable-aware) |
| M5 | **Synthetic handwriting generator** | Skeletonize, extract strokes, pen trajectories, variable width, elastic/affine jitter. Visual gallery. Tests. Deterministic from a seed | Done 2026-09-27: gallery in `docs/images/synthetic_gallery.png` |
| M6 | **Contrastive encoder** | Small CNN, 128-d L2-normalized output, InfoNCE with confusable-masked hard negatives. Ablations: synthetic-only vs. synthetic + real, and index option (a) vs. (b). Zero-shot split reported | Done 2026-09-28 (D29): synthetic + real, 30k steps on Kaggle: 86.0% top-5 (conf.), zero-shot 78.4%; real data helps zero-shot too; index (a) per font best |
| M7 | **Ranking + homoglyphs** | Score = similarity + λ·log(prior). Prior computed from Wikipedia dump character counts, source and dump date documented. Confusable groups from `confusables.txt`. Result-tile design: one tile per group, script chosen from the keyboard language | Done 2026-09-28: prior from 18 Wikipedia dumps (D25), tiles (D26); weight 0.002; shipped encoder 53.4% top-1, tiles 89.9% top-5 (conf.) |
| M8 | **Export** | int8 per-channel quantization. Compact binary weights, int8 index, charset metadata, ONNX reference. Parity fixtures (input → expected output) for the engines. Size ≤ 10 MB | Done 2026-09-28 (D27, `docs/export_format.md`): 5.02 MB; int8 export scores as the float model |
| M9 | **Web library + demo** | TypeScript engine with parity tests. Canvas demo (Vite) that shows candidates, per-query latency, and a local labelled-drawing export | Done 2026-09-27 (D28): parity on all fixtures, 20 ms per query in Node; demo without Vite (`make web-serve`) |
| M10 | **EVAL.md + Detypify comparison** | Full report. Comparison with Detypify on its symbol set, with a warning about possible overlap with Detexify training data | Done 2026-09-28 (D31): written EVAL.md; Detypify 87.8% vs glyphsketch 76.8% top-1 on its 411 symbols (possible overlap noted) |
| M11 | **Android library + demo (last)** | Pure-Kotlin engine with unit tests against the parity fixtures. ONNX Runtime benchmarked on the Pixel 8 (over Wi-Fi `adb`). Written recommendation. Compose demo. minSdk 24 (matches Thumb-Key) | Not started |
| M12 | **Later, to be decided** | Combining marks (e.g. drawn on a dotted circle ◌́). CJK as an optional index pack | Not started |

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
