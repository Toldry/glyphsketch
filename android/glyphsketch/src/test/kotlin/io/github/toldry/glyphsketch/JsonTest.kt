package io.github.toldry.glyphsketch

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class JsonTest {
    @Test
    fun parsesNestedValues() {
        val value = Json.parse("""{"a": [1, -2.5e1, true, null], "b": "x\"é\n", "c": {}}""")
        assertEquals(
            mapOf(
                "a" to listOf(1.0, -25.0, true, null),
                "b" to "x\"é\n",
                "c" to emptyMap<String, Any?>(),
            ),
            value,
        )
    }

    @Test
    fun keepsSurrogatePairs() {
        assertEquals("𝄞", Json.parse("\"\\ud834\\udd1e\""))
        assertEquals("𝄞", Json.parse("\"𝄞\""))
    }

    @Test
    fun rejectsTrailingCharacters() {
        assertThrows(IllegalArgumentException::class.java) { Json.parse("[1] 2") }
    }

    @Test
    fun readsWholeAndFractionalNumbers() {
        assertEquals(
            listOf(123.0, -7.0, 0.5, 1000.0, -13.6036, 1114111.0, 12345678901234567890.0),
            Json.parse("[123, -7, 0.5, 1e3, -13.6036, 1114111, 12345678901234567890]"),
        )
    }
}
