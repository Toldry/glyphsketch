package io.github.toldry.glyphsketch.demo

import android.content.ClipData
import android.content.ClipboardManager
import android.graphics.Bitmap
import android.graphics.Paint
import androidx.compose.foundation.Image
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.FilterQuality
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.toldry.glyphsketch.CharacterInfo
import io.github.toldry.glyphsketch.Point
import io.github.toldry.glyphsketch.Recognition
import io.github.toldry.glyphsketch.Recognizer
import io.github.toldry.glyphsketch.fromAssets
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

private val CANDIDATE_COUNTS = listOf(10, 20, 50, 100)
private const val SOURCE_URL = "https://github.com/Toldry/glyphsketch"
private const val DETAILS_URL = "https://unicodefyi.com/char/"

// Table column widths.
private val RANK_WIDTH = 32.dp
private val SCORE_WIDTH = 52.dp
private val CHAR_WIDTH = 56.dp
private val COPY_WIDTH = 44.dp
private val CODE_WIDTH = 76.dp
private val NAME_WIDTH = 300.dp
private val LOOK_ALIKES_WIDTH = 72.dp
private val LINK_WIDTH = 96.dp

@Composable
fun DemoScreen() {
    val context = LocalContext.current
    val recognizer by produceState<Recognizer?>(null) {
        value = withContext(Dispatchers.IO) { Recognizer.fromAssets(context.applicationContext) }
    }
    Surface(Modifier.fillMaxSize()) {
        val loaded = recognizer
        if (loaded == null) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text("Loading the model…")
            }
        } else {
            RecognitionScreen(loaded)
        }
    }
}

@Composable
private fun RecognitionScreen(recognizer: Recognizer) {
    val context = LocalContext.current
    val uriHandler = LocalUriHandler.current
    val strokes = remember { mutableStateListOf<List<Offset>>() }
    var strokesVersion by remember { mutableIntStateOf(0) }
    var candidateCount by remember { mutableIntStateOf(CANDIDATE_COUNTS[0]) }
    var result by remember { mutableStateOf<Recognition?>(null) }
    var text by remember { mutableStateOf("") }
    var lookAlikeMenu by remember { mutableStateOf<List<Int>?>(null) }
    var label by remember { mutableStateOf("") }
    val drawings = remember { LabelledDrawings(context.applicationContext) }
    var savedCount by remember { mutableIntStateOf(drawings.count) }
    val paint = remember { Paint() }

    fun info(codePoint: Int): CharacterInfo = recognizer.charset.characters.getValue(codePoint)

    fun code(codePoint: Int): String = "U+%04X".format(codePoint)

    /** The character as shown, or its code point when this phone has no font for it. */
    fun shown(codePoint: Int): String {
        val display = info(codePoint).displayText
        return if (paint.hasGlyph(display)) display else code(codePoint)
    }

    /** The other members of the character's look-alike group, in code point order. */
    fun lookAlikes(codePoint: Int): List<Int> =
        recognizer.ranker.members(info(codePoint).group).filter { it != codePoint }

    fun clear() {
        strokes.clear()
        strokesVersion++
    }

    fun type(codePoint: Int) {
        text += info(codePoint).text
        lookAlikeMenu = null
        clear()
    }

    fun copy(codePoint: Int) {
        val clipboard = context.getSystemService(ClipboardManager::class.java)
        clipboard.setPrimaryClip(ClipData.newPlainText(code(codePoint), info(codePoint).text))
    }

    LaunchedEffect(strokesVersion, candidateCount) {
        val drawing =
            strokes.map { stroke ->
                stroke.map { Point(it.x.toDouble(), it.y.toDouble()) }
            }
        result =
            if (drawing.isEmpty()) {
                null
            } else {
                withContext(Dispatchers.Default) {
                    recognizer.recognize(drawing, characters = candidateCount)
                }
            }
    }

    Column(
        Modifier
            .safeDrawingPadding()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("glyphsketch", style = MaterialTheme.typography.headlineMedium)
        Text("Draw a character. Everything runs on this phone; nothing is sent anywhere.")
        DrawingPad(strokes, onStrokeFinished = {
            strokes.add(it)
            strokesVersion++
        })
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = {
                if (strokes.isNotEmpty()) {
                    strokes.removeAt(strokes.size - 1)
                    strokesVersion++
                }
            }) { Text("Undo stroke") }
            OutlinedButton(onClick = ::clear) { Text("Clear") }
        }
        OutlinedTextField(text, { text = it }, Modifier.fillMaxWidth(), label = { Text("Text") })

        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                "Candidates",
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.weight(1f),
            )
            Choice("Show", candidateCount, CANDIDATE_COUNTS) { candidateCount = it }
        }
        Text(
            "Every character ranked by score. Tap a character to type it.",
            style = MaterialTheme.typography.bodySmall,
        )
        Column(Modifier.horizontalScroll(rememberScrollState())) {
            val header = MaterialTheme.typography.labelMedium
            Row(verticalAlignment = Alignment.CenterVertically) {
                Cell(RANK_WIDTH) { Text("#", style = header) }
                Cell(SCORE_WIDTH) { Text("Score", style = header) }
                Cell(CHAR_WIDTH) { Text("Char", style = header) }
                Cell(COPY_WIDTH) {}
                Cell(CODE_WIDTH) { Text("Code", style = header) }
                Cell(NAME_WIDTH) { Text("Name", style = header) }
                Cell(LOOK_ALIKES_WIDTH) { Text("Look-alikes", style = header) }
                Cell(LINK_WIDTH) {}
            }
            HorizontalDivider()
            result?.characters?.forEachIndexed { position, candidate ->
                val codePoint = candidate.codePoint
                val others = lookAlikes(codePoint)
                val small = MaterialTheme.typography.bodySmall
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Cell(RANK_WIDTH) { Text("${position + 1}", style = small) }
                    Cell(SCORE_WIDTH) { Text("%.3f".format(candidate.score), style = small) }
                    Cell(CHAR_WIDTH, Modifier.clickable { type(codePoint) }) {
                        Text(shown(codePoint), fontSize = 22.sp, maxLines = 1)
                    }
                    Cell(COPY_WIDTH, Modifier.clickable { copy(codePoint) }) { Text("📋") }
                    Cell(CODE_WIDTH) { Text(code(codePoint), style = small) }
                    Cell(NAME_WIDTH) {
                        Text(info(codePoint).name, style = small, maxLines = 1, softWrap = false)
                    }
                    Cell(
                        LOOK_ALIKES_WIDTH,
                        Modifier.clickable(others.isNotEmpty()) {
                            lookAlikeMenu = others
                        },
                    ) {
                        if (others.isNotEmpty()) {
                            val more = if (others.size > 1) " +${others.size - 1}" else ""
                            Text(shown(others[0]) + more, maxLines = 1)
                        }
                    }
                    Cell(
                        LINK_WIDTH,
                        Modifier.clickable {
                            uriHandler.openUri("$DETAILS_URL${code(codePoint)}/")
                        },
                    ) {
                        Text(
                            "unicodefyi ↗",
                            style = small,
                            color = MaterialTheme.colorScheme.primary,
                        )
                    }
                }
                HorizontalDivider()
            }
        }
        val timings = result?.timings
        Text(
            if (timings == null) {
                "Draw to see the latency."
            } else {
                "Rasterize %.1f ms · encode %.1f ms · rank %.1f ms · total %.1f ms".format(
                    timings.rasterizeMs,
                    timings.encodeMs,
                    timings.rankMs,
                    timings.totalMs,
                )
            },
            style = MaterialTheme.typography.bodySmall,
        )
        result?.let { EncoderInput(it.image, recognizer.charset.inputSize) }

        Text("Labelled drawings", style = MaterialTheme.typography.titleMedium)
        Text(
            "Save drawings with their intended character to build a personal test set. They " +
                "stay on this phone until you share them.",
            style = MaterialTheme.typography.bodySmall,
        )
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            OutlinedTextField(
                label,
                { label = it.take(4) },
                Modifier.width(96.dp),
                label = { Text("Label") },
            )
            Button(
                enabled = label.isNotEmpty() && strokes.isNotEmpty(),
                onClick = {
                    val top =
                        result
                            ?.characters
                            .orEmpty()
                            .take(5)
                            .map { info(it.codePoint).text }
                    drawings.save(label, strokes.toList(), top)
                    savedCount = drawings.count
                    label = ""
                    clear()
                },
            ) { Text("Save") }
        }
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            OutlinedButton(enabled = savedCount > 0, onClick = { drawings.share() }) {
                Text("Share JSON")
            }
            OutlinedButton(enabled = savedCount > 0, onClick = {
                drawings.deleteAll()
                savedCount = 0
            }) { Text("Delete saved") }
            Text("$savedCount saved", style = MaterialTheme.typography.bodySmall)
        }

        Text(
            recognizer.charset.attribution.joinToString(" ") +
                " Source code (AGPL-3.0): $SOURCE_URL",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }

    lookAlikeMenu?.let { members ->
        AlertDialog(
            onDismissRequest = { lookAlikeMenu = null },
            confirmButton = { TextButton(onClick = { lookAlikeMenu = null }) { Text("Close") } },
            title = { Text("Look-alikes") },
            text = {
                Column(Modifier.verticalScroll(rememberScrollState())) {
                    for (member in members) {
                        Row(
                            Modifier
                                .fillMaxWidth()
                                .clickable { type(member) }
                                .padding(vertical = 6.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                shown(member),
                                Modifier.width(64.dp),
                                fontSize = 24.sp,
                                textAlign = TextAlign.Center,
                            )
                            Column {
                                Text(info(member).name, style = MaterialTheme.typography.bodyMedium)
                                Text(code(member), style = MaterialTheme.typography.bodySmall)
                            }
                        }
                    }
                }
            },
        )
    }
}

@Composable
private fun Cell(
    width: Dp,
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit,
) {
    Box(
        modifier.width(width).padding(horizontal = 4.dp, vertical = 6.dp),
        contentAlignment = Alignment.CenterStart,
    ) { content() }
}

/** The encoder's input, magnified without smoothing. */
@Composable
private fun EncoderInput(
    image: ByteArray,
    size: Int,
) {
    val bitmap =
        remember(image) {
            val colors =
                IntArray(image.size) {
                    val shade = 255 - (image[it].toInt() and 0xFF)
                    (0xFF shl 24) or (shade * 0x010101)
                }
            Bitmap.createBitmap(colors, size, size, Bitmap.Config.ARGB_8888).asImageBitmap()
        }
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Image(bitmap, "Encoder input", Modifier.size(96.dp), filterQuality = FilterQuality.None)
        Text("Encoder input ($size×$size)", style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun Choice(
    label: String,
    selected: Int,
    options: List<Int>,
    onSelect: (Int) -> Unit,
) {
    var open by remember { mutableStateOf(false) }
    Box {
        TextButton(onClick = { open = true }) { Text("$label: $selected ▾") }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            for (option in options) {
                DropdownMenuItem(text = { Text("$option") }, onClick = {
                    onSelect(option)
                    open = false
                })
            }
        }
    }
}
