# Changelog of the Kotlin library

`io.github.toldry:glyphsketch` on Maven Central. Versions follow semantic versioning; before
1.0, a new model or an API change raises the minor version.

## Unreleased (0.1.0)

- First release: the pure-Kotlin engine and the model files as assets, loaded with
  `Recognizer.fromAssets(context)`.
- 28,711 characters: Latin, Greek, Cyrillic, Hebrew, Arabic, IPA, mathematics, symbols,
  emoji, combining marks, and every script and notation the Noto fonts cover except CJK and
  Tangut (Indic, Southeast Asian, Ethiopic, Armenian, Georgian, Canadian Syllabics,
  Egyptian and Anatolian hieroglyphs, cuneiform, runes and many more). On held-out
  Detexify, UJI and Omniglot writers: the right look-alike group among the first five tiles
  for 83.7% of drawings, first tile exactly right for 52.5% (EVAL.md).
- 9.3 MB of model files; the whole query takes about 55 ms on an x86 emulator.
- `recognize(strokes, language, tiles, characters, accept)`: tiles chosen for a keyboard
  language, ranked characters, and a filter such as `displayableOnThisDevice()`.
