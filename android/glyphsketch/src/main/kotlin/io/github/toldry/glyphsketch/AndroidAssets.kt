package io.github.toldry.glyphsketch

import android.content.Context

/**
 * Loads the recognizer from the files this library ships as assets. Takes about as long as
 * reading 6 MB and parsing the charset; call it off the main thread, once.
 */
fun Recognizer.Companion.fromAssets(context: Context): Recognizer =
    load { name -> context.assets.open(name) }
