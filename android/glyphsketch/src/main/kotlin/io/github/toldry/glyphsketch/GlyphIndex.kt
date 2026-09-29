package io.github.toldry.glyphsketch

/**
 * glyphsketch-index.bin (spec: docs/export_format.md): int8 vectors, one per font that
 * renders a character. A character's similarity is its best dot product over its vectors.
 */
public class GlyphIndex internal constructor(
    public val dims: Int,
    /** Code points, ascending; the index's column order. */
    public val codePoints: IntArray,
    /** Character k owns vectors starts[k] until starts[k + 1] (or the vector count). */
    internal val starts: IntArray,
    internal val scales: FloatArray,
    internal val values: ByteArray,
) {
    public val vectorCount: Int get() = scales.size

    /** Similarity of the embedding to every character, in the index's order. */
    public fun similarities(embedding: FloatArray): FloatArray {
        require(embedding.size == dims) { "Expected a $dims-dimensional embedding" }
        val result = FloatArray(starts.size)
        for (character in starts.indices) {
            val end = if (character + 1 < starts.size) starts[character + 1] else vectorCount
            var best = Float.NEGATIVE_INFINITY
            for (vector in starts[character] until end) {
                var dot = 0f
                val offset = vector * dims
                for (dim in 0 until dims) dot += values[offset + dim] * embedding[dim]
                dot *= scales[vector]
                if (dot > best) best = dot
            }
            result[character] = best
        }
        return result
    }

    public companion object {
        private const val MAGIC = "GSKI"
        private const val FORMAT_VERSION = 1

        public fun read(bytes: ByteArray): GlyphIndex {
            val reader = BinaryReader(bytes)
            reader.checkMagic(MAGIC, "index")
            val version = reader.u16()
            require(version == FORMAT_VERSION) { "Unsupported index format version $version" }
            val dims = reader.u16()
            val characters = reader.u32()
            val vectors = reader.u32()
            val codePoints = reader.u32Array(characters)
            val starts = reader.u32Array(characters)
            val scales = reader.float32(vectors)
            val values = reader.int8(vectors * dims)
            require(reader.atEnd()) { "Trailing bytes after the index vectors" }
            return GlyphIndex(dims, codePoints, starts, scales, values)
        }
    }
}
