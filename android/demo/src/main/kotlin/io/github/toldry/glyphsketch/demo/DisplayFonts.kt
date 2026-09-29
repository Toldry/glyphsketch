package io.github.toldry.glyphsketch.demo

import android.content.Context
import android.graphics.Paint
import android.graphics.Typeface
import androidx.compose.ui.text.font.FontFamily
import java.util.concurrent.ConcurrentHashMap

/**
 * Chooses a font for showing a character: the phone's own fonts when they have it,
 * otherwise one of the subsets in assets/fonts (made by glyphsketch.tools.display_fonts),
 * otherwise none, and the caller shows the code point.
 */
class DisplayFonts(
    context: Context,
) {
    private val bundled: List<Pair<Paint, FontFamily>> =
        context.assets
            .list(DIRECTORY)
            .orEmpty()
            .filter { it.endsWith(".ttf") }
            .sorted()
            .map { name ->
                val typeface = Typeface.createFromAsset(context.assets, "$DIRECTORY/$name")
                Paint().apply { this.typeface = typeface } to FontFamily(typeface)
            }
    private val system = Paint()
    private val cache = ConcurrentHashMap<String, Choice>()

    sealed interface Choice {
        data object System : Choice

        data class Bundled(
            val family: FontFamily,
        ) : Choice

        data object Missing : Choice
    }

    fun choose(text: String): Choice =
        cache.getOrPut(text) {
            when {
                system.hasGlyph(text) -> {
                    Choice.System
                }

                else -> {
                    bundled.firstOrNull { (paint, _) -> paint.hasGlyph(text) }?.let {
                        Choice.Bundled(it.second)
                    } ?: Choice.Missing
                }
            }
        }

    companion object {
        private const val DIRECTORY = "fonts"
    }
}
