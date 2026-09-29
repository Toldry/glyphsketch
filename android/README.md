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

## In Android Studio

1. **Get the repository onto the machine that runs Android Studio**, the whole repository
   rather than just `android/`: the build reads the model files from `../export/`. On the
   Windows host that is the folder the devcontainer mounts (e.g. `C:\...\GlyphSketch`),
   or a fresh `git clone https://github.com/Toldry/glyphsketch`.
2. **Open the `android` folder**: *File → Open…*, choose `GlyphSketch\android` (the folder
   with `settings.gradle.kts`), and trust the project. Opening the repository root instead
   won't find the Gradle build.
3. **Let Gradle sync.** The project uses Android Gradle Plugin 9.4.1 and Gradle 9.7.1 (the
   wrapper downloads it). If Studio says it is too old for the plugin, update it
   (*Help → Check for Updates*). If it asks for Android SDK Platform 37, accept the install.
   The Gradle JDK must be 17 or newer; Studio's bundled JDK works (*Settings → Build,
   Execution, Deployment → Build Tools → Gradle → Gradle JDK*). Studio writes
   `local.properties` with your SDK path; it is ignored by git.
4. **Create a virtual device**: *Tools → Device Manager → +* (*Create Virtual Device*),
   pick a phone (e.g. Pixel 8) and a recent system image (API 35 or newer, x86_64 on an
   Intel or AMD PC). Any image from API 24 up works.
5. **Run the demo**: choose the `demo` run configuration in the toolbar, pick the virtual
   device and press *Run* (▶). Draw with the mouse on the pad.
6. **Run the unit tests**: in the *Project* view, right-click
   `glyphsketch/src/test/kotlin` → *Run 'Tests in …'*. They include parity with
   `export/fixtures.json`.
7. **Run the benchmark**: open *Build → Select Build Variant…* and set `benchmark` to
   `release` (debug builds are much slower and would skew the timings). Choose the
   `benchmark` run configuration and run it. The results appear on screen and in *Logcat*;
   filter it with `tag:GlyphsketchBench` for the one-line JSON report.

**What emulator timings mean.** An x86_64 emulator runs on the PC's processor with hardware
virtualization, so its timings are the PC's, not a phone's: typically several times faster
than a mid-range phone. They are still a fair comparison between the Kotlin engine and ONNX
Runtime, which run on the same emulated device. An ARM64 system image on an x86 PC is
translated and far slower, so don't use one for timings.

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
