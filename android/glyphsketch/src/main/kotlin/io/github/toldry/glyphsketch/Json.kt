package io.github.toldry.glyphsketch

/**
 * A small JSON reader for glyphsketch-charset.json and the parity fixtures, so the library
 * has no dependencies (Android's org.json is not available in JVM unit tests).
 *
 * Objects become [Map], arrays [List], numbers [Double], and `true`/`false`/`null` their
 * Kotlin values.
 */
internal object Json {
    fun parse(text: String): Any? {
        val parser = Parser(text)
        parser.skipWhitespace()
        val value = parser.value()
        parser.skipWhitespace()
        if (!parser.atEnd()) parser.fail("trailing characters")
        return value
    }

    private class Parser(
        private val text: String,
    ) {
        private var position = 0

        fun atEnd(): Boolean = position >= text.length

        fun fail(message: String): Nothing =
            throw IllegalArgumentException("Invalid JSON at character $position: $message")

        fun skipWhitespace() {
            while (position < text.length && text[position] in " \t\r\n") position++
        }

        private fun expect(char: Char) {
            if (position >= text.length || text[position] != char) fail("expected '$char'")
            position++
        }

        fun value(): Any? {
            if (atEnd()) fail("unexpected end")
            return when (val char = text[position]) {
                '{' -> {
                    objectValue()
                }

                '[' -> {
                    arrayValue()
                }

                '"' -> {
                    stringValue()
                }

                't' -> {
                    literal("true", true)
                }

                'f' -> {
                    literal("false", false)
                }

                'n' -> {
                    literal("null", null)
                }

                else -> {
                    if (char == '-' ||
                        char.isDigit()
                    ) {
                        numberValue()
                    } else {
                        fail("unexpected '$char'")
                    }
                }
            }
        }

        private fun literal(
            word: String,
            result: Any?,
        ): Any? {
            if (!text.startsWith(word, position)) fail("expected $word")
            position += word.length
            return result
        }

        private fun objectValue(): Map<String, Any?> {
            expect('{')
            val result = LinkedHashMap<String, Any?>()
            skipWhitespace()
            if (position < text.length && text[position] == '}') {
                position++
                return result
            }
            while (true) {
                skipWhitespace()
                val key = stringValue()
                skipWhitespace()
                expect(':')
                skipWhitespace()
                result[key] = value()
                skipWhitespace()
                if (position < text.length && text[position] == ',') {
                    position++
                    continue
                }
                expect('}')
                return result
            }
        }

        private fun arrayValue(): List<Any?> {
            expect('[')
            val result = ArrayList<Any?>()
            skipWhitespace()
            if (position < text.length && text[position] == ']') {
                position++
                return result
            }
            while (true) {
                skipWhitespace()
                result.add(value())
                skipWhitespace()
                if (position < text.length && text[position] == ',') {
                    position++
                    continue
                }
                expect(']')
                return result
            }
        }

        private fun stringValue(): String {
            expect('"')
            val builder = StringBuilder()
            while (true) {
                if (atEnd()) fail("unterminated string")
                val char = text[position++]
                when (char) {
                    '"' -> {
                        return builder.toString()
                    }

                    '\\' -> {
                        if (atEnd()) fail("unterminated escape")
                        when (val escaped = text[position++]) {
                            '"', '\\', '/' -> {
                                builder.append(escaped)
                            }

                            'b' -> {
                                builder.append('\b')
                            }

                            'f' -> {
                                builder.append('\u000C')
                            }

                            'n' -> {
                                builder.append('\n')
                            }

                            'r' -> {
                                builder.append('\r')
                            }

                            't' -> {
                                builder.append('\t')
                            }

                            'u' -> {
                                if (position + 4 > text.length) fail("short \\u escape")
                                val hex = text.substring(position, position + 4)
                                builder.append(
                                    hex.toIntOrNull(16)?.toChar() ?: fail("bad \\u escape"),
                                )
                                position += 4
                            }

                            else -> {
                                fail("unknown escape \\$escaped")
                            }
                        }
                    }

                    else -> {
                        builder.append(char)
                    }
                }
            }
        }

        /**
         * Whole numbers (code points, most of the charset) are read digit by digit; others go
         * to Double.parseDouble. Kotlin's toDoubleOrNull screens every string with a large
         * regular expression first, which made loading the charset take seconds on a phone.
         */
        private fun numberValue(): Double {
            val start = position
            val negative = text[position] == '-'
            if (negative) position++
            var whole = 0L
            var digits = 0
            while (position < text.length && text[position] in '0'..'9' && digits < 18) {
                whole = whole * 10 + (text[position] - '0')
                position++
                digits++
            }
            val simple = position >= text.length || text[position] !in ".eE0123456789"
            if (digits > 0 && simple) return if (negative) -whole.toDouble() else whole.toDouble()
            while (position < text.length && text[position] in "0123456789.eE+-") position++
            return try {
                java.lang.Double.parseDouble(text.substring(start, position))
            } catch (_: NumberFormatException) {
                fail("bad number")
            }
        }
    }
}

@Suppress("UNCHECKED_CAST")
internal fun Any?.asObject(): Map<String, Any?> =
    this as? Map<String, Any?> ?: throw IllegalArgumentException("Expected a JSON object")

@Suppress("UNCHECKED_CAST")
internal fun Any?.asArray(): List<Any?> =
    this as? List<Any?> ?: throw IllegalArgumentException("Expected a JSON array")

internal fun Any?.asDouble(): Double =
    this as? Double ?: throw IllegalArgumentException("Expected a JSON number")

internal fun Any?.asString(): String =
    this as? String ?: throw IllegalArgumentException("Expected a JSON string")
