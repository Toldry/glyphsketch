package io.github.toldry.glyphsketch.demo

import android.content.ClipData
import android.content.ClipboardManager
import android.graphics.Bitmap
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.FilterQuality
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.toldry.glyphsketch.CharacterInfo
import io.github.toldry.glyphsketch.Point
import io.github.toldry.glyphsketch.Recognition
import io.github.toldry.glyphsketch.Recognizer
import io.github.toldry.glyphsketch.fromAssets
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private val CANDIDATE_COUNTS = listOf(10, 20, 50, 100)
private const val SOURCE_URL = "https://github.com/Toldry/glyphsketch"
private const val DETAILS_URL = "https://unicodefyi.com/char/"

// The web demo's table text is 0.85 rem of 15 px, its notes 0.8 rem.
private val TABLE_SIZE = 13.sp
private val SMALL_SIZE = 12.sp

@Composable
fun DemoScreen() {
    val context = LocalContext.current
    val colors = LocalWebColors.current
    val loaded by produceState<Pair<Recognizer, DisplayFonts>?>(null) {
        value =
            withContext(Dispatchers.IO) {
                val application = context.applicationContext
                Recognizer.fromAssets(application) to DisplayFonts(application)
            }
    }
    Box(Modifier.fillMaxSize().background(colors.paper)) {
        val ready = loaded
        if (ready == null) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text("Loading the model…", color = colors.muted)
            }
        } else {
            RecognitionScreen(ready.first, ready.second)
        }
    }
}

@Composable
private fun RecognitionScreen(
    recognizer: Recognizer,
    fonts: DisplayFonts,
) {
    val context = LocalContext.current
    val colors = LocalWebColors.current
    val density = LocalDensity.current.density
    val uriHandler = LocalUriHandler.current
    val scope = rememberCoroutineScope()
    val strokes = remember { mutableStateListOf<List<Offset>>() }
    var strokesVersion by remember { mutableIntStateOf(0) }
    var candidateCount by remember { mutableIntStateOf(CANDIDATE_COUNTS[0]) }
    var result by remember { mutableStateOf<Recognition?>(null) }
    var text by remember { mutableStateOf("") }
    var label by remember { mutableStateOf("") }
    var labelFocused by remember { mutableStateOf(false) }
    var linkText by remember { mutableStateOf("Link") }
    val drawings = remember { LabelledDrawings(context.applicationContext) }
    var savedMessage by remember { mutableStateOf(savedCountText(drawings.count)) }

    fun info(codePoint: Int): CharacterInfo = recognizer.charset.characters.getValue(codePoint)

    fun code(codePoint: Int): String = "U+%04X".format(codePoint)

    fun describe(codePoint: Int): String = "${code(codePoint)} ${info(codePoint).name}"

    /** The other members of the character's look-alike group, in code point order. */
    fun lookAlikes(codePoint: Int): List<Int> =
        recognizer.ranker.members(info(codePoint).group).filter { it != codePoint }

    /** As the web demo: append to the text and use it as the label; the drawing stays. */
    fun type(codePoint: Int) {
        text += info(codePoint).text
        label = info(codePoint).text
    }

    fun clipboard(): ClipboardManager = context.getSystemService(ClipboardManager::class.java)

    fun changed() {
        strokesVersion++
    }

    LaunchedEffect(strokesVersion, candidateCount) {
        val drawing =
            strokes.map { stroke -> stroke.map { Point(it.x.toDouble(), it.y.toDouble()) } }
        result =
            if (drawing.isEmpty()) {
                null
            } else {
                withContext(Dispatchers.Default) {
                    recognizer.recognize(drawing, characters = candidateCount)
                }
            }
        val top = result?.characters?.firstOrNull()
        if (top != null && !labelFocused) label = info(top.codePoint).text.trim()
    }

    Column(
        Modifier
            .safeDrawingPadding()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
    ) {
        Text("glyphsketch", fontSize = 24.sp, fontWeight = FontWeight.Bold)
        Text(
            "Draw a character. Everything runs on this phone; nothing is sent anywhere.",
            color = colors.muted,
            modifier = Modifier.padding(vertical = 12.dp),
        )
        DrawingPad(
            strokes,
            onStrokeFinished = {
                strokes.add(it)
                changed()
            },
            Modifier.widthIn(max = 340.dp),
        )
        Controls {
            WebButton(onClick = {
                if (strokes.isNotEmpty()) strokes.removeAt(strokes.size - 1)
                changed()
            }) { Text("Undo stroke") }
            WebButton(onClick = {
                strokes.clear()
                changed()
            }) { Text("Clear") }
            WebButton(onClick = {
                if (strokes.isEmpty()) return@WebButton
                // Pixels → dp, which match the web pad's CSS pixels.
                val inDp = strokes.map { stroke -> stroke.map { it.x / density to it.y / density } }
                clipboard().setPrimaryClip(
                    ClipData.newPlainText("glyphsketch drawing", DrawingLink.url(inDp)),
                )
                scope.launch {
                    linkText = "Link copied"
                    delay(1500)
                    linkText = "Link"
                }
            }) { Text(linkText) }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Text ")
            WebTextField(text, { text = it }, Modifier.fillMaxWidth(), fontSize = 20.sp)
        }

        Row(
            Modifier.fillMaxWidth().padding(top = 18.dp, bottom = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text("Candidates", fontSize = 16.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.weight(1f))
            Text("Show ", color = colors.muted, fontSize = 14.sp)
            CountChooser(candidateCount) { candidateCount = it }
        }
        Text(
            "Every character ranked by score. Tap a character to type it.",
            color = colors.muted,
            fontSize = SMALL_SIZE,
            modifier = Modifier.padding(bottom = 8.dp),
        )
        CandidatesTable(
            result,
            show = { codePoint, size ->
                Glyph(info(codePoint).displayText, codePoint, fonts, size)
            },
            name = { info(it).name },
            describe = ::describe,
            code = ::code,
            lookAlikes = ::lookAlikes,
            onType = ::type,
            onCopy = {
                clipboard().setPrimaryClip(ClipData.newPlainText(code(it), info(it).text))
            },
            onDetails = { uriHandler.openUri("$DETAILS_URL${code(it)}/") },
        )
        val timings = result?.timings
        Text(
            if (timings == null) {
                "Draw a character."
            } else {
                "%.1f ms per query: rasterize %.1f, encode %.1f, rank %.1f.".format(
                    timings.totalMs,
                    timings.rasterizeMs,
                    timings.encodeMs,
                    timings.rankMs,
                )
            },
            color = colors.muted,
            modifier = Modifier.padding(vertical = 12.dp),
        )
        EncoderInput(result?.image, recognizer.charset.inputSize)

        Text(
            "Labelled drawings",
            fontSize = 16.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(top = 18.dp, bottom = 6.dp),
        )
        Text(
            "Save drawings with their intended character to build a personal test set. They " +
                "stay on this phone until you export them.",
        )
        Controls {
            WebTextField(
                label,
                { label = it.take(4) },
                Modifier.width(80.dp).onFocusChanged { labelFocused = it.isFocused },
                placeholder = "Label",
            )
            WebButton(onClick = {
                val trimmed = label.trim()
                if (strokes.isEmpty() || trimmed.codePointCount(0, trimmed.length) != 1) {
                    savedMessage = "Draw something and give it a one-character label first."
                    return@WebButton
                }
                val top =
                    result
                        ?.characters
                        .orEmpty()
                        .take(5)
                        .map { info(it.codePoint).text }
                drawings.save(trimmed, strokes.toList(), top)
                strokes.clear()
                changed()
                savedMessage = savedCountText(drawings.count)
            }) { Text("Save drawing") }
            WebButton(onClick = { if (drawings.count > 0) drawings.share() }) {
                Text("Export JSON")
            }
            WebButton(onClick = {
                drawings.deleteAll()
                savedMessage = savedCountText(0)
            }) { Text("Delete saved") }
        }
        Text(savedMessage, color = colors.muted)

        Text(
            recognizer.charset.attribution.joinToString(" ") +
                "\n\nSource code (AGPL-3.0): ${SOURCE_URL.removePrefix("https://")}",
            color = colors.muted,
            fontSize = SMALL_SIZE,
            modifier = Modifier.padding(top = 32.dp),
        )
    }
}

private fun savedCountText(count: Int): String =
    when (count) {
        0 -> "No drawings saved."
        1 -> "1 drawing saved."
        else -> "$count drawings saved."
    }

/** A row of controls with the web demo's 8 px gaps, wrapping like its flex rows. */
@Composable
private fun Controls(content: @Composable () -> Unit) {
    FlowRow(
        Modifier.padding(vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) { content() }
}

/** An input as the web demo draws them: panel background, thin border. */
@Composable
private fun WebTextField(
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    fontSize: TextUnit = BODY_SIZE,
    placeholder: String = "",
) {
    val colors = LocalWebColors.current
    val shape = RoundedCornerShape(6.dp)
    BasicTextField(
        value,
        onValueChange,
        modifier
            .background(colors.panel, shape)
            .border(1.dp, colors.line, shape)
            .padding(horizontal = 10.dp, vertical = 4.dp),
        singleLine = true,
        textStyle = TextStyle(color = colors.ink, fontSize = fontSize),
        cursorBrush = SolidColor(colors.accent),
        decorationBox = { inner ->
            Box {
                if (value.isEmpty()) Text(placeholder, color = colors.muted, fontSize = fontSize)
                inner()
            }
        },
    )
}

@Composable
private fun CountChooser(
    selected: Int,
    onSelect: (Int) -> Unit,
) {
    val colors = LocalWebColors.current
    var open by remember { mutableStateOf(false) }
    Box {
        WebButton(onClick = { open = true }) { Text("$selected ▾", fontSize = 14.sp) }
        DropdownMenu(
            expanded = open,
            onDismissRequest = { open = false },
            containerColor = colors.paper,
            border = BorderStroke(1.dp, colors.line),
        ) {
            for (option in CANDIDATE_COUNTS) {
                Text(
                    "$option",
                    Modifier
                        .clickable {
                            onSelect(option)
                            open = false
                        }.padding(horizontal = 16.dp, vertical = 8.dp),
                )
            }
        }
    }
}

/** A character in a font that has it, or its code point when no font here does. */
@Composable
private fun Glyph(
    text: String,
    codePoint: Int,
    fonts: DisplayFonts,
    size: TextUnit,
) {
    when (val choice = fonts.choose(text)) {
        DisplayFonts.Choice.System -> {
            Text(text, fontSize = size, maxLines = 1)
        }

        is DisplayFonts.Choice.Bundled -> {
            Text(text, fontSize = size, fontFamily = choice.family, maxLines = 1)
        }

        DisplayFonts.Choice.Missing -> {
            val muted = LocalWebColors.current.muted
            Text("%04X".format(codePoint), fontSize = 9.sp, color = muted, maxLines = 1)
        }
    }
}

private class TableColumn(
    val width: Dp,
    val alignEnd: Boolean = false,
)

private val RANK = TableColumn(28.dp, alignEnd = true)
private val SCORE = TableColumn(52.dp, alignEnd = true)
private val CHAR = TableColumn(56.dp)
private val COPY = TableColumn(44.dp)
private val CODE = TableColumn(72.dp)
private val NAME = TableColumn(340.dp)
private val LOOK_ALIKES = TableColumn(84.dp)
private val DETAILS = TableColumn(96.dp)

@Composable
private fun CandidatesTable(
    result: Recognition?,
    show: @Composable (codePoint: Int, size: TextUnit) -> Unit,
    name: (Int) -> String,
    describe: (Int) -> String,
    code: (Int) -> String,
    lookAlikes: (Int) -> List<Int>,
    onType: (Int) -> Unit,
    onCopy: (Int) -> Unit,
    onDetails: (Int) -> Unit,
) {
    val colors = LocalWebColors.current
    val scope = rememberCoroutineScope()
    val cell = TextStyle(fontSize = TABLE_SIZE)
    val muted = cell.copy(color = colors.muted)
    val header = muted.copy(fontWeight = FontWeight.SemiBold)
    Column(Modifier.horizontalScroll(rememberScrollState())) {
        Row(Modifier.bottomLine(colors.line), verticalAlignment = Alignment.CenterVertically) {
            Cell(RANK) { Text("#", style = header) }
            Cell(SCORE) { Text("Score", style = header) }
            Cell(CHAR) { Text("Char", style = header) }
            Cell(COPY) {}
            Cell(CODE) { Text("Code", style = header) }
            Cell(NAME) { Text("Name", style = header) }
            Cell(LOOK_ALIKES) { Text("Look-alikes", style = header) }
            Cell(DETAILS) {}
        }
        result?.characters?.forEachIndexed { position, candidate ->
            val codePoint = candidate.codePoint
            val others = lookAlikes(codePoint)
            var copied by remember(codePoint) { mutableStateOf(false) }
            var menuOpen by remember(codePoint) { mutableStateOf(false) }
            Row(Modifier.bottomLine(colors.line), verticalAlignment = Alignment.CenterVertically) {
                Cell(RANK) { Text("${position + 1}", style = muted) }
                Cell(SCORE) { Text("%.3f".format(candidate.score), style = muted) }
                Cell(CHAR) {
                    WebButton(onClick = { onType(codePoint) }, Modifier.widthIn(min = 40.dp)) {
                        show(codePoint, 21.sp)
                    }
                }
                Cell(COPY) {
                    WebButton(onClick = {
                        onCopy(codePoint)
                        scope.launch {
                            copied = true
                            delay(1200)
                            copied = false
                        }
                    }) { Text(if (copied) "✓" else "📋", style = cell) }
                }
                Cell(CODE) { Text(code(codePoint), style = muted) }
                Cell(NAME) { Text(name(codePoint), style = cell, maxLines = 1, softWrap = false) }
                Cell(LOOK_ALIKES) {
                    if (others.isNotEmpty()) {
                        Box {
                            WebButton(
                                onClick = { menuOpen = true },
                                Modifier.widthIn(min = 44.dp),
                            ) {
                                Row(verticalAlignment = Alignment.Bottom) {
                                    show(others[0], 17.sp)
                                    if (others.size > 1) {
                                        Text(
                                            " +${others.size - 1}",
                                            style = muted,
                                            fontSize = 10.sp,
                                        )
                                    }
                                }
                            }
                            LookAlikeMenu(
                                open = menuOpen,
                                members = others,
                                show = show,
                                describe = describe,
                                onDismiss = { menuOpen = false },
                            ) {
                                menuOpen = false
                                onType(it)
                            }
                        }
                    }
                }
                Cell(DETAILS) {
                    Text(
                        "unicodefyi ↗",
                        Modifier.clickable { onDetails(codePoint) },
                        style = cell.copy(color = colors.accent),
                        maxLines = 1,
                    )
                }
            }
        }
    }
}

/** The web demo's chooser: a floating list of the look-alikes with their codes and names. */
@Composable
private fun LookAlikeMenu(
    open: Boolean,
    members: List<Int>,
    show: @Composable (codePoint: Int, size: TextUnit) -> Unit,
    describe: (Int) -> String,
    onDismiss: () -> Unit,
    onChoose: (Int) -> Unit,
) {
    val colors = LocalWebColors.current
    DropdownMenu(
        expanded = open,
        onDismissRequest = onDismiss,
        modifier = Modifier.widthIn(max = 360.dp),
        containerColor = colors.paper,
        shape = RoundedCornerShape(8.dp),
        border = BorderStroke(1.dp, colors.line),
    ) {
        for (member in members) {
            Row(
                Modifier
                    .fillMaxWidth()
                    .clickable { onChoose(member) }
                    .padding(horizontal = 10.dp, vertical = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Box(Modifier.width(36.dp), contentAlignment = Alignment.Center) {
                    show(member, 22.sp)
                }
                Text(describe(member), color = colors.muted, fontSize = SMALL_SIZE)
            }
        }
    }
}

@Composable
private fun Cell(
    column: TableColumn,
    content: @Composable () -> Unit,
) {
    Box(
        Modifier
            .width(column.width)
            .height(44.dp)
            .padding(horizontal = 6.dp, vertical = 2.dp),
        contentAlignment = if (column.alignEnd) Alignment.CenterEnd else Alignment.CenterStart,
    ) { content() }
}

/** The web table's row borders. */
private fun Modifier.bottomLine(color: Color): Modifier =
    drawBehind {
        drawLine(color, Offset(0f, size.height), Offset(size.width, size.height), 1.dp.toPx())
    }

/** The encoder's input, magnified without smoothing; blank before the first stroke. */
@Composable
private fun EncoderInput(
    image: ByteArray?,
    size: Int,
) {
    val colors = LocalWebColors.current
    val bitmap =
        remember(image) {
            val pixels =
                IntArray(size * size) {
                    val ink = (image?.get(it)?.toInt() ?: 0) and 0xFF
                    (0xFF shl 24) or ((255 - ink) * 0x010101)
                }
            Bitmap.createBitmap(pixels, size, size, Bitmap.Config.ARGB_8888).asImageBitmap()
        }
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Image(
            bitmap,
            "Encoder input",
            Modifier.size(96.dp).border(1.dp, colors.line),
            filterQuality = FilterQuality.None,
        )
        Text("Encoder input ($size×$size)", color = colors.muted)
    }
}
