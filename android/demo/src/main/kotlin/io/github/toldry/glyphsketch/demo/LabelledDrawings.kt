package io.github.toldry.glyphsketch.demo

import android.content.Context
import android.content.Intent
import androidx.compose.ui.geometry.Offset
import androidx.core.content.FileProvider
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/**
 * Drawings saved with the character they were meant to be, for a personal test set. The
 * export has the web demo's format (`{"format": 1, "drawings": [...]}`), so both go through
 * the same evaluation. Stored one JSON object per line in the app's private files.
 */
class LabelledDrawings(
    private val context: Context,
) {
    private val file = File(context.filesDir, "labelled-drawings.jsonl")

    val count: Int
        get() = if (file.exists()) file.useLines { lines -> lines.count(String::isNotBlank) } else 0

    fun save(
        label: String,
        strokes: List<List<Offset>>,
        language: String,
        tiles: List<String>,
    ) {
        val strokesJson =
            strokes.joinToString(",", "[", "]") { stroke ->
                stroke.joinToString(",", "[", "]") { "[${round(it.x)},${round(it.y)}]" }
            }
        val tilesJson = tiles.joinToString(",", "[", "]") { quote(it) }
        val line =
            "{\"label\":${quote(label)},\"strokes\":$strokesJson,\"language\":${quote(language)}," +
                "\"tiles\":$tilesJson,\"savedAt\":${quote(now())}}"
        file.appendText(line + "\n")
    }

    fun deleteAll() {
        file.delete()
    }

    /** Opens the share sheet with the export as a file. */
    fun share() {
        val lines = if (file.exists()) file.readLines().filter { it.isNotBlank() } else emptyList()
        val directory = File(context.cacheDir, "exports").apply { mkdirs() }
        val export = File(directory, "glyphsketch-drawings-${now().take(10)}.json")
        export.writeText("{\"format\":1,\"drawings\":[\n" + lines.joinToString(",\n") + "\n]}\n")
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.files", export)
        val send =
            Intent(Intent.ACTION_SEND)
                .setType("application/json")
                .putExtra(Intent.EXTRA_STREAM, uri)
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        context.startActivity(
            Intent.createChooser(send, null).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
        )
    }

    private fun round(value: Float): String = "%.1f".format(Locale.ROOT, value)

    private fun now(): String =
        SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.ROOT)
            .apply { timeZone = TimeZone.getTimeZone("UTC") }
            .format(Date())

    private fun quote(text: String): String {
        val builder = StringBuilder("\"")
        for (char in text) {
            when {
                char == '"' -> builder.append("\\\"")
                char == '\\' -> builder.append("\\\\")
                char < ' ' -> builder.append("\\u%04x".format(char.code))
                else -> builder.append(char)
            }
        }
        return builder.append('"').toString()
    }
}
