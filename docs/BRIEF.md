# Original project brief

This is the brief the project started from (2026-09-27), kept verbatim. Where it conflicts
with a later decision in `PLAN.md` or `DECISIONS.md`, the later decision wins. In
particular, Android work comes last and the web demo is the development test bench.

## Goal
Build a library that recognizes a hand-drawn character on a phone screen and returns
ranked Unicode candidates, covering as many Unicode characters as practical. It will be
integrated into Thumb-Key (https://github.com/dessalines/thumb-key), an AGPL-3.0,
privacy-focused Android keyboard written in Kotlin/Jetpack Compose and distributed on
F-Droid. This is a separate repository; Thumb-Key integration comes later.

## Hard constraints
- Fully offline at runtime. No network access, no Google Play Services, no ML Kit.
- Everything must be buildable from source, as F-Droid requires.
- License: AGPL-3.0 for our code. Every font, dataset and dependency must be compatible,
  and each one must be recorded in `THIRD_PARTY.md` with its license and URL.
  Verify each license from the source itself; don't assume.
- Budget: model + glyph index under ~10 MB in the APK; under ~50 ms per query on a
  mid-range phone.
- Adding a new character must NOT require new handwriting data. This is the key idea.

## Approach (challenge it if you see a better one, but explain why)
Retrieval instead of classification:

    user drawing  ──► encoder ──► embedding ─┐
                                             ├─► nearest neighbours ─► candidates
    font glyphs   ──► encoder ──► precomputed index (shipped with the app)

1. Character set: enumerate candidates from the Unicode Character Database. Exclude
   unassigned, private use, control, format, whitespace and surrogate code points.
   Start with a v0 set (Latin incl. extended blocks, IPA, Greek, Cyrillic, Hebrew,
   Arabic, math operators, arrows, letterlike symbols, currency, misc. symbols,
   dingbats). Defer CJK (too large for v0), but design so it can be added later.
2. Glyphs: render each character from free fonts (e.g. the Noto family under OFL,
   GNU Unifont). Use fontTools to check cmap coverage and never render a fallback or
   .notdef glyph. Render several fonts per character where available.
3. Training data:
   - Synthetic: generate "hand-drawn-looking" versions of rendered glyphs
     (skeletonize, vary stroke width, elastic distortion, jitter, rotation, and simulated
     pen strokes). This is what lets the character set scale.
   - Real: Detexify's stroke data (ODbL; attribution required) and other openly licensed
     handwritten-symbol datasets you can find and verify. Hold out a real test set.
4. Model: a small CNN encoder on rasterized input (e.g. 64×64), trained contrastively
   (InfoNCE or similar) so drawings land near their glyphs. Mine hard negatives among
   visually similar characters.
5. Homoglyphs: characters such as Latin A / Greek Α / Cyrillic А render identically.
   Group them into confusable sets (see Unicode's confusables.txt) and design how results
   show them, e.g. one tile with a script chooser or a bias toward the keyboard's
   current language.
6. Ranking: combine embedding similarity with a character-frequency prior so common
   characters beat obscure look-alikes. Keep the prior small and documented.

## Deliverables
- `training/`: Python (PyTorch) pipeline: charset builder, renderer, synthetic data
  generator, training, evaluation, export. Reproducible from one documented command.
- `export/`: quantized model (int8) + glyph index + charset metadata.
- `web/`: TypeScript library with a tiny demo web app (drawing canvas → candidate list).
- `android/`: Kotlin library with a tiny demo app (drawing canvas → candidate list).
  Evaluate two inference options and recommend one: ONNX Runtime for Android vs. a
  hand-written pure-Kotlin implementation of the small CNN (no native deps, simpler for
  F-Droid).
- `EVAL.md`: top-1/top-5 accuracy on the held-out real set, broken down by Unicode
  block, with a confusable-aware variant (a prediction in the right confusable group
  counts as correct). Include a comparison against Detypify on its supported symbols.
- `DECISIONS.md`: a running log of design decisions and trade-offs.

## Environment
- Development: VS Code devcontainer (`.devcontainer/`) on a Windows 11 host, Claude Code
  in auto mode inside it.
- Test devices: Windows: ASUS Zenbook Duo UX8406MA; Android: Pixel 8. Android minSdk 24
  (matches Thumb-Key).
