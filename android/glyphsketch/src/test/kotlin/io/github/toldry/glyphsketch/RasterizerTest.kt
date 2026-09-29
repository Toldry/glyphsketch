package io.github.toldry.glyphsketch

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class RasterizerTest {
    private fun pixel(
        image: ByteArray,
        row: Int,
        column: Int,
    ): Int = image[row * 64 + column].toInt() and 0xFF

    @Test
    fun aTapBecomesACentredRoundDot() {
        val image = Rasterizer.rasterize(listOf(listOf(Point(5.0, 5.0))))
        assertEquals(64 * 64, image.size)
        assertEquals(255, pixel(image, 32, 32))
        assertEquals(0, pixel(image, 0, 0))
        assertEquals(pixel(image, 32, 31), pixel(image, 31, 32))
    }

    @Test
    fun aHorizontalLineSpansSevenEighthsPlusItsRoundCaps() {
        val image = Rasterizer.rasterize(listOf(listOf(Point(0.0, 0.0), Point(100.0, 0.0))))
        val inked = (0 until 64).filter { pixel(image, 32, it) > 127 }
        assertEquals(3, inked.first()) // as training/src/glyphsketch/strokes.py at 64 px
        assertEquals(60, inked.last())
    }

    @Test
    fun simplificationKeepsTheCornerAndDropsCollinearPoints() {
        val points =
            listOf(
                Point(0.0, 0.0),
                Point(1.0, 0.0),
                Point(2.0, 0.0),
                Point(2.0, 1.0),
                Point(2.0, 2.0),
            )
        assertEquals(
            listOf(Point(0.0, 0.0), Point(2.0, 0.0), Point(2.0, 2.0)),
            Rasterizer.simplifyStroke(points, 0.25),
        )
    }

    @Test
    fun anEmptyDrawingIsRejected() {
        assertThrows(
            IllegalArgumentException::class.java,
        ) { Rasterizer.rasterize(listOf(emptyList())) }
    }

    @Test
    fun combiningMarksAreShownOnADottedCircle() {
        val acute = CharacterInfo(0x301, "COMBINING ACUTE ACCENT", "", "Inherited", "Mn", 0x301, 0f)
        assertEquals("◌́", acute.displayText)
        assertEquals("́", acute.text)
        assertEquals("A", acute.copy(codePoint = 0x41, generalCategory = "Lu").displayText)
    }

    @Test
    fun theBoundingBoxRasterizerDrawsExactlyWhatComparingEveryPixelDraws() {
        val random = java.util.Random(7)
        repeat(20) { drawing ->
            val segments = DoubleArray(4 * (1 + drawing * 3)) { random.nextDouble() * 70 - 3 }
            if (drawing % 4 == 0) { // a tap: a zero-length segment
                segments[2] = segments[0]
                segments[3] = segments[1]
            }
            val expected = bruteForce(segments, 64, 2.5)
            val actual = Rasterizer.rasterizeSegments(segments, 64, 2.5)
            assertEquals("drawing $drawing", expected.toList(), actual.toList())
        }
    }

    /** Every pixel against every segment. */
    private fun bruteForce(
        segments: DoubleArray,
        size: Int,
        penWidth: Double,
    ): ByteArray {
        val image = ByteArray(size * size)
        for (pixel in image.indices) {
            val px = pixel % size + 0.5
            val py = pixel / size + 0.5
            var nearest = Double.POSITIVE_INFINITY
            for (index in segments.indices step 4) {
                val ax = segments[index]
                val ay = segments[index + 1]
                val dx = segments[index + 2] - ax
                val dy = segments[index + 3] - ay
                val lengthSquared = dx * dx + dy * dy
                val t =
                    if (lengthSquared >
                        0
                    ) {
                        ((px - ax) * dx + (py - ay) * dy) / lengthSquared
                    } else {
                        0.0
                    }
                val clamped = t.coerceIn(0.0, 1.0)
                nearest =
                    minOf(nearest, Math.hypot(px - (ax + clamped * dx), py - (ay + clamped * dy)))
            }
            val ink = (penWidth / 2 + 0.5 - nearest).coerceIn(0.0, 1.0)
            image[pixel] = Math.rint((ink.toFloat() * 255f).toDouble()).toInt().toByte()
        }
        return image
    }
}
