package io.github.toldry.glyphsketch.demo

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.dp

/**
 * A square pad that records strokes in its own pixels. `onStrokeFinished` runs when the pen
 * lifts; a tap is a stroke of one point.
 */
@Composable
fun DrawingPad(
    strokes: List<List<Offset>>,
    onStrokeFinished: (List<Offset>) -> Unit,
    modifier: Modifier = Modifier,
) {
    val current = remember { mutableStateListOf<Offset>() }
    val ink = MaterialTheme.colorScheme.onSurface
    val paper = MaterialTheme.colorScheme.surfaceContainerHighest
    Canvas(
        modifier
            .fillMaxWidth()
            .aspectRatio(1f)
            .clip(RoundedCornerShape(8.dp))
            .pointerInput(Unit) {
                awaitEachGesture {
                    val down = awaitFirstDown()
                    current.clear()
                    current.add(down.position)
                    down.consume()
                    while (true) {
                        val event = awaitPointerEvent()
                        val change = event.changes.firstOrNull { it.id == down.id } ?: break
                        if (!change.pressed) break
                        change.historical.forEach { current.add(it.position) }
                        current.add(change.position)
                        change.consume()
                    }
                    val finished = current.toList()
                    current.clear()
                    onStrokeFinished(finished)
                }
            },
    ) {
        drawRect(paper)
        val width = PEN_WIDTH_DP.dp.toPx()
        val pen = Stroke(width = width, cap = StrokeCap.Round, join = StrokeJoin.Round)
        for (stroke in strokes + listOf(current.toList())) {
            if (stroke.isEmpty()) continue
            if (stroke.size == 1) {
                drawCircle(ink, radius = width / 2, center = stroke[0])
                continue
            }
            val path = Path()
            path.moveTo(stroke[0].x, stroke[0].y)
            for (point in stroke.drop(1)) path.lineTo(point.x, point.y)
            drawPath(path, ink, style = pen)
        }
    }
}

private const val PEN_WIDTH_DP = 5f
