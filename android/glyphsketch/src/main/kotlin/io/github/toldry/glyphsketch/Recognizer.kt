package io.github.toldry.glyphsketch

import java.io.InputStream

/** The result of one query, with timings in milliseconds. */
public class Recognition internal constructor(
    public val tiles: List<Tile>,
    public val characters: List<Candidate>,
    /** The 64×64 input image, row-major, 0 paper to 255 ink (read the bytes unsigned). */
    public val image: ByteArray,
    public val timings: Timings,
) {
    public data class Timings(
        public val rasterizeMs: Double,
        public val encodeMs: Double,
        public val rankMs: Double,
    ) {
        public val totalMs: Double get() = rasterizeMs + encodeMs + rankMs
    }
}

/**
 * The whole engine: strokes → result tiles and ranked characters. Load it once (about
 * 100 ms); it is immutable and can be queried from any thread.
 */
public class Recognizer(
    public val model: Model,
    public val index: GlyphIndex,
    public val charset: Charset,
) {
    public val ranker: Ranker = Ranker(index.codePoints, charset)

    init {
        require(model.embeddingDim == index.dims && charset.embeddingDim == index.dims) {
            "Model, index and charset disagree on the embedding size"
        }
    }

    /** The scripts a keyboard in `language` types (a key of the charset's keyboard
     * scripts); Latin for unknown languages. */
    public fun scriptsFor(language: String?): List<String> =
        language?.let { charset.keyboardScripts[it] } ?: listOf("Latin")

    /**
     * Recognize one drawing: `tiles` look-alike groups with their representative for a
     * keyboard in `language`, and the best `characters` characters. `accept` limits both,
     * e.g. to characters the phone can show ([displayableOnThisDevice] on Android).
     */
    public fun recognize(
        strokes: List<Stroke>,
        language: String? = null,
        tiles: Int = 5,
        characters: Int = 10,
        accept: CharacterFilter? = null,
    ): Recognition {
        val start = System.nanoTime()
        val image = Rasterizer.rasterize(strokes, charset.rasterization)
        val rasterized = System.nanoTime()
        val embedding = model.embed(image)
        val encoded = System.nanoTime()
        val ranking = ranker.rank(index.similarities(embedding))
        val tileList = ranker.tiles(ranking, tiles, scriptsFor(language), accept)
        val characterList = ranker.topCharacters(ranking, characters, accept)
        val ranked = System.nanoTime()
        return Recognition(
            tileList,
            characterList,
            image,
            Recognition.Timings(
                (rasterized - start) / 1e6,
                (encoded - rasterized) / 1e6,
                (ranked - encoded) / 1e6,
            ),
        )
    }

    public companion object {
        public const val MODEL_FILE: String = "glyphsketch-model.bin"
        public const val INDEX_FILE: String = "glyphsketch-index.bin"
        public const val CHARSET_FILE: String = "glyphsketch-charset.json"

        public fun fromFiles(
            model: ByteArray,
            index: ByteArray,
            charsetJson: String,
        ): Recognizer =
            Recognizer(Model.read(model), GlyphIndex.read(index), Charset.parse(charsetJson))

        /** Load the three exported files by name, e.g. `{ context.assets.open(it) }` on
         * Android. */
        public fun load(open: (String) -> InputStream): Recognizer =
            fromFiles(
                open(MODEL_FILE).use { it.readBytes() },
                open(INDEX_FILE).use { it.readBytes() },
                open(CHARSET_FILE).use { it.readBytes().toString(Charsets.UTF_8) },
            )
    }
}
