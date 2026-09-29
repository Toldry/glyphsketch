package io.github.toldry.glyphsketch.demo

import android.graphics.Bitmap
import android.graphics.Paint
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.Image
import androidx.compose.foundation.border
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
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
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.toldry.glyphsketch.CharacterInfo
import io.github.toldry.glyphsketch.Point
import io.github.toldry.glyphsketch.Recognition
import io.github.toldry.glyphsketch.Recognizer
import io.github.toldry.glyphsketch.Tile
import io.github.toldry.glyphsketch.fromAssets
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.Locale

private val CANDIDATE_COUNTS = listOf(10, 20, 50, 100)
private const val SOURCE_URL = "https://github.com/Toldry/glyphsketch"

@Composable
fun DemoScreen() {
    val context = LocalContext.current
    val recognizer by produceState<Recognizer?>(null) {
        value = withContext(Dispatchers.IO) { Recognizer.fromAssets(context.applicationContext) }
    }
    Surface(Modifier.fillMaxSize()) {
        val loaded = recognizer
        if (loaded == null) {
            Box(
                Modifier.fillMaxSize(),
                contentAlignment = Alignment.Center,
            ) { Text("Loading the model…") }
        } else {
            RecognitionScreen(loaded)
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun RecognitionScreen(recognizer: Recognizer) {
    val context = LocalContext.current
    val strokes = remember { mutableStateListOf<List<Offset>>() }
    var strokesVersion by remember { mutableIntStateOf(0) }
    val languages =
        remember {
            recognizer.charset.keyboardScripts.keys
                .sorted()
        }
    var language by remember {
        mutableStateOf(Locale.getDefault().language.takeIf { it in languages } ?: "en")
    }
    var candidateCount by remember { mutableIntStateOf(CANDIDATE_COUNTS[0]) }
    var result by remember { mutableStateOf<Recognition?>(null) }
    var text by remember { mutableStateOf("") }
    var chooser by remember { mutableStateOf<Tile?>(null) }
    var label by remember { mutableStateOf("") }
    val drawings = remember { LabelledDrawings(context.applicationContext) }
    var savedCount by remember { mutableIntStateOf(drawings.count) }
    val paint = remember { Paint() }

    fun info(codePoint: Int): CharacterInfo = recognizer.charset.characters.getValue(codePoint)

    /** The character as shown, or its code point when this phone has no font for it. */
    fun shown(codePoint: Int): String {
        val info = info(codePoint)
        return if (paint.hasGlyph(
                info.displayText,
            )
        ) {
            info.displayText
        } else {
            "U+%04X".format(codePoint)
        }
    }

    fun clear() {
        strokes.clear()
        strokesVersion++
    }

    fun type(codePoint: Int) {
        text += info(codePoint).text
        chooser = null
        clear()
    }

    LaunchedEffect(strokesVersion, language, candidateCount) {
        val drawing =
            strokes.map { stroke ->
                stroke.map { Point(it.x.toDouble(), it.y.toDouble()) }
            }
        result =
            if (drawing.isEmpty()) {
                null
            } else {
                withContext(Dispatchers.Default) {
                    recognizer.recognize(drawing, language = language, characters = candidateCount)
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
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            OutlinedButton(onClick = {
                if (strokes.isNotEmpty()) {
                    strokes.removeAt(strokes.size - 1)
                    strokesVersion++
                }
            }) { Text("Undo stroke") }
            OutlinedButton(onClick = ::clear) { Text("Clear") }
            Spacer(Modifier.weight(1f))
            Choice("Keyboard", language, languages, { it }) { language = it }
        }
        Text(
            "Some characters look the same when drawn, such as Latin A, Greek Α and Cyrillic А. " +
                "Each tile stands for one such group and shows the member your keyboard's " +
                "language uses: A with English, Α with Greek. The others are in the tile's " +
                "menu. The setting doesn't change what is recognized, only which look-alike a " +
                "tile shows.",
            style = MaterialTheme.typography.bodySmall,
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            val tiles = result?.tiles.orEmpty()
            for (position in 0 until 5) {
                val tile = tiles.getOrNull(position)
                Box(
                    Modifier
                        .weight(1f)
                        .height(64.dp)
                        .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(8.dp))
                        .let { box ->
                            if (tile == null) {
                                box
                            } else {
                                box.combinedClickable(
                                    onClick = { type(tile.representative) },
                                    onLongClick = { chooser = tile },
                                )
                            }
                        },
                    contentAlignment = Alignment.Center,
                ) {
                    if (tile != null) {
                        val shownText = shown(tile.representative)
                        Text(shownText, fontSize = if (shownText.startsWith("U+")) 11.sp else 30.sp)
                        if (tile.members.size > 1) {
                            Text(
                                "+${tile.members.size - 1}",
                                Modifier.align(Alignment.BottomEnd).padding(4.dp),
                                style = MaterialTheme.typography.labelSmall,
                            )
                        }
                    }
                }
            }
        }
        Text(
            "Tap a tile to type it; long-press for its look-alikes.",
            style = MaterialTheme.typography.bodySmall,
        )
        OutlinedTextField(text, { text = it }, Modifier.fillMaxWidth(), label = { Text("Text") })

        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                "Candidates",
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.weight(1f),
            )
            Choice("Show", candidateCount, CANDIDATE_COUNTS, { it.toString() }) {
                candidateCount =
                    it
            }
        }
        Text(
            "Every character ranked by score, look-alikes listed separately.",
            style = MaterialTheme.typography.bodySmall,
        )
        result?.characters?.forEachIndexed { position, candidate ->
            val info = info(candidate.codePoint)
            Row(
                Modifier
                    .fillMaxWidth()
                    .combinedClickable(onClick = { type(candidate.codePoint) }),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    "${position + 1}.",
                    Modifier.width(36.dp),
                    style = MaterialTheme.typography.bodySmall,
                )
                Text(shown(candidate.codePoint), Modifier.width(72.dp), fontSize = 20.sp)
                Column(Modifier.weight(1f)) {
                    Text(
                        info.name.lowercase(Locale.ROOT),
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    Text(
                        "U+%04X · %s · score %.3f".format(
                            candidate.codePoint,
                            info.block,
                            candidate.score,
                        ),
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
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
                    val tiles = result?.tiles.orEmpty().map { info(it.representative).text }
                    drawings.save(label, strokes.toList(), language, tiles)
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
            OutlinedButton(
                enabled = savedCount > 0,
                onClick = { drawings.share() },
            ) { Text("Share JSON") }
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

    chooser?.let { tile ->
        AlertDialog(
            onDismissRequest = { chooser = null },
            confirmButton = { TextButton(onClick = { chooser = null }) { Text("Close") } },
            title = { Text("Look-alikes") },
            text = {
                Column(Modifier.verticalScroll(rememberScrollState())) {
                    for (member in tile.members) {
                        Row(
                            Modifier
                                .fillMaxWidth()
                                .combinedClickable(onClick = { type(member) })
                                .padding(vertical = 6.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                shown(member),
                                Modifier.width(64.dp),
                                fontSize = 24.sp,
                                textAlign = TextAlign.Center,
                            )
                            Text(
                                info(member).name.lowercase(Locale.ROOT),
                                style = MaterialTheme.typography.bodyMedium,
                            )
                        }
                    }
                }
            },
        )
    }
}

/** The encoder's input, magnified without smoothing. */
@Composable
private fun EncoderInput(
    image: ByteArray,
    size: Int,
) {
    val bitmap =
        remember(image) {
            val pixels = IntArray(image.size) { 255 - (image[it].toInt() and 0xFF) }
            val colors = IntArray(pixels.size) { (0xFF shl 24) or (pixels[it] * 0x010101) }
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
private fun <T> Choice(
    label: String,
    selected: T,
    options: List<T>,
    name: (T) -> String,
    onSelect: (T) -> Unit,
) {
    var open by remember { mutableStateOf(false) }
    Box {
        TextButton(onClick = { open = true }) { Text("$label: ${name(selected)} ▾") }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            for (option in options) {
                DropdownMenuItem(text = { Text(name(option)) }, onClick = {
                    onSelect(option)
                    open = false
                })
            }
        }
    }
}
