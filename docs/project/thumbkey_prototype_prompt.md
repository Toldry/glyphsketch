# Prompt: prototype handwriting input in Thumb-Key with glyphsketch

You're building a prototype of a new Thumb-Key feature: the user draws a character with a
finger and picks it from the recognizer's candidates, which is useful for symbols,
accented letters and other scripts that aren't on the keyboard. The recognizer already
exists as a Kotlin library, `io.github.toldry:glyphsketch:0.1.1`, on Maven Central. A UX
design for the feature already exists. Read it first and follow it; where it's silent or
conflicts with the constraints below, say so rather than guess.

You have two codebases:

- **Thumb-Key** (https://github.com/dessalines/thumb-key): an AGPL-3.0 Android keyboard in
  Kotlin and Jetpack Compose, distributed on F-Droid. This is where you work.
- **glyphsketch** (https://github.com/Toldry/glyphsketch): the recognizer, its training
  pipeline, a web demo and an Android demo. Read it for reference; **don't change it**.
  If the library lacks something the feature needs, write down what and why, and work
  around it in Thumb-Key for the prototype.

## What to deliver

A working prototype on a branch of Thumb-Key, in small commits with clear messages, that
builds, passes Thumb-Key's own checks (`./gradlew lintKotlin`, its tests) and runs in the
Android emulator. Don't push, and don't open a pull request: the maintainer of glyphsketch
will open the PR themselves. At the end, report what you built, how to try it, what you
measured, what deviates from the design and why, and any open questions.

## Hard constraints

- **Fully offline.** No network access at runtime, and no Google Play Services or ML Kit.
  glyphsketch runs entirely on the device.
- **F-Droid.** Everything builds from source; no proprietary or prebuilt native code. The
  library is pure Kotlin with no dependencies besides the Kotlin standard library, so it
  qualifies. Don't add ONNX Runtime or any other native inference library: glyphsketch's
  DECISIONS.md, D36, explains why it was rejected (33 MB of native code, F-Droid).
- **AGPL-3.0**, like both projects. Any new dependency must be license-compatible.
- **Thumb-Key's toolchain.** Keep Thumb-Key's own versions (Android Gradle Plugin 9.4.1
  with built-in Kotlin, Kotlin 2.4.20, compile SDK 37, minSdk 24, JVM 17 target). The
  library was built with the same ones.
- **Attribution.** The model was trained on data that requires attribution (Detexify under
  the ODbL, UJI Pen Characters under CC BY 4.0, Omniglot, Wikipedia, the Unicode Character
  Database). Show `recognizer.charset.attribution` (a list of sentences) somewhere the user
  can find it, such as Thumb-Key's about screen. The library also ships `LICENSE`,
  `NOTICE.md` and `Unicode-3.0.txt` under `META-INF/glyphsketch/` in its AAR.

## Adding the dependency

```kotlin
// app/build.gradle.kts
dependencies {
    implementation("io.github.toldry:glyphsketch:0.1.1")
}
```

Maven Central is already in Thumb-Key's repositories. The AAR brings its model files as
assets (`glyphsketch-model.bin`, `glyphsketch-index.bin`, `glyphsketch-charset.json`,
about 9.3 MB uncompressed), which Android merges into the APK automatically; nothing to
copy. It needs no ProGuard or R8 rules (no reflection), and no permissions.

## Using the library

The public API is small. The source is `android/glyphsketch/src/main/kotlin/` in the
glyphsketch repository; `android/README.md` there has a summary.

```kotlin
import io.github.toldry.glyphsketch.Point
import io.github.toldry.glyphsketch.Recognizer
import io.github.toldry.glyphsketch.displayableOnThisDevice
import io.github.toldry.glyphsketch.fromAssets

// Once, off the main thread: reads the model files and parses the charset.
val recognizer: Recognizer = Recognizer.fromAssets(context)

// Per query, also off the main thread. Strokes are lists of points in any unit (pixels
// are fine), x to the right, y down; a stroke of one point is a tap (a dot).
val strokes: List<List<Point>> = listOf(listOf(Point(10.0, 10.0), Point(40.0, 80.0)))
val result = recognizer.recognize(
    strokes,
    language = "en",                    // the keyboard's language, see below
    tiles = 5,                          // look-alike groups to return
    characters = 10,                    // ranked characters to return
    accept = displayableOnThisDevice(), // optional: only characters the phone can show
)
```

**What comes back** (`Recognition`):

- `result.tiles`: `List<Tile>`, best first. A tile is one *look-alike group*. Some
  characters can't be told apart when drawn, such as Latin A, Greek Α and Cyrillic А, or
  o, O and some 60 round letters of other scripts. `tile.representative` is the code point
  to show on the tile. `tile.members` is the whole group, representative first, ordered
  for the keyboard's language; that's what a long-press menu should list. `tile.score` is
  its score.
- `result.characters`: `List<Candidate>`, every character ranked separately (`codePoint`,
  `score`, `similarity`).
- `result.timings`: rasterize, encode and rank in milliseconds, and `totalMs`.
- `result.image`: the 64×64 image the encoder saw (bytes, 0 paper to 255 ink; read them
  unsigned), which helps when debugging.

**Showing and typing a character.** Look up metadata with
`recognizer.charset.characters.getValue(codePoint)`, a `CharacterInfo` with `name`,
`block`, `script`, `generalCategory` and more. Show `info.displayText`: combining marks
(accents, Indic vowel signs) are shown on a dotted circle ◌́ so they're visible. Insert
`info.text`: the bare character, which combines with the character before the cursor.
`recognizer.ranker.members(group)` lists a group in code point order, if the design wants
that rather than the language order.

**The keyboard language** only decides which member of a look-alike group represents a
tile, and the order of the group's members. It never changes what is recognized or how it
ranks. Pass the language code of Thumb-Key's current layout. The codes the library knows
are in `recognizer.charset.keyboardScripts`: ar, bg, cs, de, el, en, es, fa, fr, he, it,
pl, pt, ru, sr, tr, uk and vi. Any other code, or `null`, means Latin. Mapping Thumb-Key's
layouts to these codes is part of your work; for layouts in another script (Hindi, Thai),
Latin is the fallback for now.

**Which characters it knows.** 28,711: Latin, Greek, Cyrillic, Hebrew, Arabic, IPA,
mathematics, arrows, symbols, emoji (monochrome shapes), combining marks, and most scripts
and notations the Noto fonts cover (Indic, Southeast Asian, Ethiopic, Armenian, Georgian,
Canadian Syllabics, runes, cuneiform, hieroglyphs and many more), but no CJK and no
Tangut. **Filtering** with `displayableOnThisDevice()` keeps only characters the phone's
fonts can draw. Phones have far fewer fonts than desktops, so without it many candidates
would show as boxes, and typing a character that shows as a box helps nobody. You can also
pass your own `CharacterFilter`, a `(CharacterInfo) -> Boolean`.

**Threading and performance.** `Recognizer` is immutable and thread-safe. Create it once
per process (the input method service lives long; keep the instance) on a background
dispatcher, and never on the main thread. Loading reads about 9 MB of assets, so measure it
on the emulator and report it. Recognize on `Dispatchers.Default`, after each stroke ends
(pen up), and cancel a previous query if a new stroke arrives. Measured on an x86_64
emulator: about 55 ms per query (rasterize, encode, rank). A real mid-range phone may be
several times slower; the budget is 300 ms. Don't recognize on every pointer move.

**Accuracy to expect.** On held-out writers of real handwriting datasets (mostly maths
symbols, letters and digits): the right look-alike group is among the first five tiles
for 84% of drawings, and the first tile is exactly right for 53%. Plan the UI around
choosing from several candidates, not around the first one. Details are in glyphsketch's
`EVAL.md`.

## Reference implementations to read

In the glyphsketch repository:

- `android/demo/src/main/kotlin/io/github/toldry/glyphsketch/demo/DrawingPad.kt`: a
  Compose drawing pad that records strokes with pointer input, including taps. Reuse it
  or adapt it.
- `android/demo/src/main/kotlin/io/github/toldry/glyphsketch/demo/DemoScreen.kt`: loading
  the recognizer with `produceState`, recognizing in a `LaunchedEffect` on
  `Dispatchers.Default`, a candidates list and a look-alike popup.
- `android/demo/.../DisplayFonts.kt`: how the demo falls back to bundled fonts for
  characters the phone lacks. Thumb-Key should prefer the `displayableOnThisDevice()`
  filter over bundling fonts (the demo's fonts are 6.4 MB); decide with the design.
- `web/demo/` and the live web demo (https://toldry.github.io/glyphsketch/web/demo/), to
  try the recognizer by hand.
- `DECISIONS.md` (D26 on tiles and keyboard languages, D36 on the Android engine, D38 on
  fonts) and `docs/export_format.md` (the model files, and what a tile is).

## How to work

1. Read the design, Thumb-Key's structure (how its keyboard layouts, keys and the
   `KeyboardScreen` Compose UI in `ui/components/keyboard/` fit together, the input method
   service `IMEService.kt`, how it switches modes, and where settings
   live) and glyphsketch's `android/README.md` and demo code, before writing code.
2. Write a short plan: where the entry point to handwriting goes (a key or mode, per the
   design), the drawing surface, the candidate strip, the look-alike menu, how a choice is
   committed through the `InputConnection`, what a setting looks like if the design has
   one, and how you'll map layouts to language codes. Check it against the design.
3. Build it in small steps that each compile and run: dependency and loading first, then
   the drawing surface, then recognition and candidates, then committing text, then
   look-alikes, then polish.
4. Test in the Android emulator in Android Studio (an x86_64 system image). Measure the
   load time and per-query latency (`result.timings`) and report them. Check a Latin, a
   Greek or Cyrillic, and a symbol drawing, a combining accent, and a look-alike choice.
5. Keep Thumb-Key's code style (it uses kotlinter/ktlint) and add tests where Thumb-Key has
   them for similar code.
6. Don't change the glyphsketch codebase. Note library problems, with how to reproduce
   them, in your final report.
