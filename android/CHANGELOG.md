# Changelog of the Kotlin library

`io.github.toldry:glyphsketch` on Maven Central. Versions follow semantic versioning; before
1.0, a new model or an API change raises the minor version.

## Unreleased (0.1.0)

- First release: the pure-Kotlin engine and the model files as assets, loaded with
  `Recognizer.fromAssets(context)`.
- 11,791 characters (Latin, Greek, Cyrillic, Hebrew, Arabic, IPA, mathematics, symbols,
  emoji, combining marks, Egyptian hieroglyphs; no CJK). On held-out Detexify, UJI and
  Omniglot writers: the right look-alike group among the first five tiles for 86.4% of
  drawings, first tile exactly right for 54.1% (EVAL.md).
- `recognize(strokes, language, tiles, characters, accept)`: tiles chosen for a keyboard
  language, ranked characters, and a filter such as `displayableOnThisDevice()`.
