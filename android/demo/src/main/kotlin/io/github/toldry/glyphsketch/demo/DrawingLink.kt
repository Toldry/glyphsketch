package io.github.toldry.glyphsketch.demo

import java.util.Base64
import kotlin.math.roundToLong

/**
 * Links to a drawing in the web demo, in the format of web/demo/drawingLink.ts: "1" then
 * base64url bytes; per stroke its point count, then each point as the change from the
 * previous point in tenths of a pixel, as zigzag varints.
 */
object DrawingLink {
    const val WEB_DEMO_URL = "https://toldry.github.io/glyphsketch/web/demo/"
    const val PARAMETER = "d"
    private const val FORMAT = "1"

    fun url(strokes: List<List<Pair<Float, Float>>>): String =
        "$WEB_DEMO_URL?$PARAMETER=${encode(strokes)}"

    fun encode(strokes: List<List<Pair<Float, Float>>>): String {
        val bytes = java.io.ByteArrayOutputStream()
        var previousX = 0L
        var previousY = 0L
        for (stroke in strokes) {
            writeVarint(bytes, stroke.size.toLong())
            for ((x, y) in stroke) {
                val tenthsX = roundHalfUp(x * 10.0)
                val tenthsY = roundHalfUp(y * 10.0)
                writeVarint(bytes, zigzag(tenthsX - previousX))
                writeVarint(bytes, zigzag(tenthsY - previousY))
                previousX = tenthsX
                previousY = tenthsY
            }
        }
        return FORMAT + Base64.getUrlEncoder().withoutPadding().encodeToString(bytes.toByteArray())
    }

    /** JavaScript's Math.round: halves go up. */
    private fun roundHalfUp(value: Double): Long = kotlin.math.floor(value + 0.5).roundToLong()

    private fun zigzag(value: Long): Long = if (value >= 0) 2 * value else -2 * value - 1

    private fun writeVarint(
        bytes: java.io.ByteArrayOutputStream,
        value: Long,
    ) {
        var rest = value
        while (rest >= 0x80) {
            bytes.write(((rest and 0x7F) or 0x80).toInt())
            rest = rest shr 7
        }
        bytes.write(rest.toInt())
    }
}
