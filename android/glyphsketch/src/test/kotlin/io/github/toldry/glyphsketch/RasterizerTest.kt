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
}
