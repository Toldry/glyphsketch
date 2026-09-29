package io.github.toldry.glyphsketch

import android.content.Context
import android.graphics.Paint

/**
 * Loads the recognizer from the files this library ships as assets. Takes about as long as
 * reading 6 MB and parsing the charset; call it off the main thread, once.
 */
public fun Recognizer.Companion.fromAssets(context: Context): Recognizer =
    load { name -> context.assets.open(name) }

/**
 * A [CharacterFilter] that accepts the characters this device's fonts can show (combining
 * marks on their dotted circle). Typing a character that shows as a box helps nobody.
 * Results are cached; the filter is thread-safe.
 */
public fun displayableOnThisDevice(): CharacterFilter {
    val paint =
        object : ThreadLocal<Paint>() {
            override fun initialValue(): Paint = Paint() // withInitial needs API 26
        }
    val cache = java.util.concurrent.ConcurrentHashMap<Int, Boolean>()
    return { info -> cache.getOrPut(info.codePoint) { paint.get()!!.hasGlyph(info.displayText) } }
}
