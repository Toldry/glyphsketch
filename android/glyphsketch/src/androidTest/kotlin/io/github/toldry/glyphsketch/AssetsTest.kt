package io.github.toldry.glyphsketch

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** On a device or emulator: the library loads from its own assets and recognizes an A. */
@RunWith(AndroidJUnit4::class)
class AssetsTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext

    @Test
    fun loadsFromAssetsAndRecognizesAnA() {
        val recognizer = Recognizer.fromAssets(context)
        val strokes =
            listOf(
                listOf(Point(0.0, 100.0), Point(50.0, 0.0), Point(100.0, 100.0)),
                listOf(Point(25.0, 55.0), Point(75.0, 55.0)),
            )
        val result = recognizer.recognize(strokes, language = "en")
        assertEquals(5, result.tiles.size)
        assertTrue(result.tiles.any { 0x41 in it.members })
        assertTrue(result.timings.totalMs > 0)
    }

    @Test
    fun theDisplayFilterAcceptsBasicLatin() {
        val recognizer = Recognizer.fromAssets(context)
        val displayable = displayableOnThisDevice()
        assertTrue(displayable(recognizer.charset.characters.getValue(0x41)))
    }
}
