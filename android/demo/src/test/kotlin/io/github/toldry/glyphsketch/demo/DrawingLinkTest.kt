package io.github.toldry.glyphsketch.demo

import org.junit.Assert.assertEquals
import org.junit.Test

class DrawingLinkTest {
    @Test
    fun encodesLikeTheWebDemo() {
        // Expected value from web/demo/drawingLink.ts for the same strokes.
        val strokes =
            listOf(
                listOf(10.04f to 20f, 30.5f to 25.25f, 300f to 0f),
                listOf(5f to 5f),
                listOf(0f to 339.9f, 12.3f to 1.1f),
            )
        assertEquals(WEB_ENCODING, DrawingLink.encode(strokes))
    }

    companion object {
        const val WEB_ENCODING = "1A8gBkAOaA2qOKvkDAYsuZAJjqjT2Afc0"
    }
}
