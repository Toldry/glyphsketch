# android

Kotlin inference library, a small Jetpack Compose demo app and a benchmark app (M11).
minSdk 24 and the build toolchain match Thumb-Key (Gradle 9.7.1, Android Gradle Plugin
9.4.1, Kotlin 2.4.20, JVM 17).

| Module | What it is |
|--------|------------|
| `glyphsketch` | The engine: a pure-Kotlin port of `web/src` with no dependencies besides the Kotlin standard library. Ships the files in `../export/` as assets. |
| `demo` | Drawing pad, ranked candidates, latency, and labelled drawings you can share as JSON. |
| `benchmark` | Times the Kotlin encoder against ONNX Runtime on the phone. The only module that uses ONNX Runtime; not for distribution. |

## Using the library

```kotlin
// Once, off the main thread (reads about 6 MB and parses the charset).
val recognizer = Recognizer.fromAssets(context)

// Per query: strokes in any unit, x to the right, y down.
val strokes = listOf(listOf(Point(10.0, 10.0), Point(40.0, 80.0)))
val result = recognizer.recognize(strokes, language = "en", tiles = 5, characters = 10)
result.tiles        // one per look-alike group, representative chosen for the keyboard language
result.characters   // every character ranked by score
result.timings      // rasterize, encode and rank, in milliseconds
```

Show a character with `CharacterInfo.displayText` (a combining mark sits on a dotted
circle) and insert `CharacterInfo.text`. `recognizer.ranker.members(group)` lists a
look-alike group in code point order. `recognizer.charset.attribution` belongs in the
app's about screen.

## Building and testing

```sh
./gradlew lintKotlin                      # ktlint, lines up to 100 characters
./gradlew :glyphsketch:testDebugUnitTest  # JVM tests, including parity with export/fixtures.json
./gradlew :demo:assembleDebug             # demo/build/outputs/apk/debug/demo-debug.apk
```

The parity tests read `../export/` directly, so run the export stage first if it's
missing.

## On a phone over Wi-Fi

On the phone: Developer options → Wireless debugging → Pair device with pairing code. Then:

```sh
adb pair <ip>:<pairing port> <code>
adb connect <ip>:<connect port>
./gradlew :demo:installDebug
./gradlew :benchmark:installRelease
adb shell am start -n io.github.toldry.glyphsketch.benchmark/.BenchmarkActivity
adb logcat -s GlyphsketchBench            # one JSON line with the timings
```

Labelled drawings saved in the demo can also be read without the share sheet:
`adb shell run-as io.github.toldry.glyphsketch.demo cat files/labelled-drawings.jsonl`.
