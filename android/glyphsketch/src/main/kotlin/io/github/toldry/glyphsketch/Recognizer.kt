package io.github.toldry.glyphsketch

import java.io.InputStream

/** The result of one query, with timings in milliseconds. */
class Recognition(
    val tiles: List<Tile>,
    val characters: List<Candidate>,
    /** The 64×64 input image, row-major, 0 paper to 255 ink (read the bytes unsigned). */
    val image: ByteArray,
    val timings: Timings,
) {
    data class Timings(
        val rasterizeMs: Double,
        val encodeMs: Double,
        val rankMs: Double,
    ) {
        val totalMs: Double get() = rasterizeMs + encodeMs + rankMs
    }
}

/**
 * The whole engine: strokes → result tiles and ranked characters. Load it once (about
 * 100 ms); it is immutable and can be queried from any thread.
 */
class Recognizer(
    val model: Model,
    val index: GlyphIndex,
    val charset: Charset,
) {
    val ranker = Ranker(index.codePoints, charset)

    init {
        require(model.embeddingDim == index.dims && charset.embeddingDim == index.dims) {
            "Model, index and charset disagree on the embedding size"
        }
    }

    /** The scripts a keyboard in `language` types (a key of the charset's keyboard
     * scripts); Latin for unknown languages. */
    fun scriptsFor(language: String?): List<String> =
        language?.let { charset.keyboardScripts[it] } ?: listOf("Latin")

    fun recognize(
        strokes: List<Stroke>,
        language: String? = null,
        tiles: Int = 5,
        characters: Int = 10,
    ): Recognition {
        val start = System.nanoTime()
        val image = Rasterizer.rasterize(strokes, charset.rasterization)
        val rasterized = System.nanoTime()
        val embedding = model.embed(image)
        val encoded = System.nanoTime()
        val ranking = ranker.rank(index.similarities(embedding))
        val tileList = ranker.tiles(ranking, tiles, scriptsFor(language))
        val characterList = ranker.topCharacters(ranking, characters)
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

    companion object {
        const val MODEL_FILE = "glyphsketch-model.bin"
        const val INDEX_FILE = "glyphsketch-index.bin"
        const val CHARSET_FILE = "glyphsketch-charset.json"

        fun fromFiles(
            model: ByteArray,
            index: ByteArray,
            charsetJson: String,
        ): Recognizer =
            Recognizer(Model.read(model), GlyphIndex.read(index), Charset.parse(charsetJson))

        /** Load the three exported files by name, e.g. `{ context.assets.open(it) }` on
         * Android. */
        fun load(open: (String) -> InputStream): Recognizer =
            fromFiles(
                open(MODEL_FILE).use { it.readBytes() },
                open(INDEX_FILE).use { it.readBytes() },
                open(CHARSET_FILE).use { it.readBytes().toString(Charsets.UTF_8) },
            )
    }
}
