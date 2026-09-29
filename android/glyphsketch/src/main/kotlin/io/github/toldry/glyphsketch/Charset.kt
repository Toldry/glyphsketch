package io.github.toldry.glyphsketch

/** One character of glyphsketch-charset.json. */
public data class CharacterInfo(
    public val codePoint: Int,
    public val name: String,
    public val block: String,
    /** UCD script name; `Common` for symbols, `Inherited` for most combining marks. */
    public val script: String,
    /** UCD general category, e.g. `Lu`, `Nd`, `Sm`, `Mn`. */
    public val generalCategory: String,
    /** The confusable group: its smallest code point. */
    public val group: Int,
    public val logPrior: Float,
) {
    /** The character itself, what typing it inserts. */
    public val text: String get() = String(Character.toChars(codePoint))

    /** How to show the character on its own: a combining mark sits on a dotted circle
     * (◌́) so it is visible. */
    public val displayText: String
        get() = if (isCombiningMark) DOTTED_CIRCLE + text else text

    public val isCombiningMark: Boolean get() = generalCategory.startsWith("M")

    public companion object {
        public const val DOTTED_CIRCLE: String = "\u25CC"
    }
}

/** glyphsketch-charset.json: per-character metadata and the ranking settings. */
public class Charset internal constructor(
    public val unicodeVersion: String,
    public val inputSize: Int,
    public val embeddingDim: Int,
    public val rasterization: RasterizationSettings,
    public val priorWeight: Double,
    /** Keyboard language code → the scripts a keyboard in that language types. */
    public val keyboardScripts: Map<String, List<String>>,
    public val characters: Map<Int, CharacterInfo>,
    /** Show it in the app's about screen. */
    public val attribution: List<String>,
) {
    public companion object {
        public fun parse(json: String): Charset {
            val raw = Json.parse(json).asObject()
            val format = raw["format"].asDouble().toInt()
            require(format == 1) { "Unsupported charset format $format" }
            val columns = raw["columns"].asArray().map { it.asString() }

            fun position(name: String): Int {
                val position = columns.indexOf(name)
                require(position >= 0) { "Charset column $name is missing" }
                return position
            }
            val codePoint = position("code_point")
            val name = position("name")
            val block = position("block")
            val script = position("script")
            val category = position("general_category")
            val group = position("group")
            val logPrior = position("log_prior")
            val characters = LinkedHashMap<Int, CharacterInfo>()
            for (item in raw["characters"].asArray()) {
                val row = item.asArray()
                val info =
                    CharacterInfo(
                        codePoint = row[codePoint].asDouble().toInt(),
                        name = row[name].asString(),
                        block = row[block].asString(),
                        script = row[script].asString(),
                        generalCategory = row[category].asString(),
                        group = row[group].asDouble().toInt(),
                        logPrior = row[logPrior].asDouble().toFloat(),
                    )
                characters[info.codePoint] = info
            }
            val raster = raw["rasterization"].asObject()
            val inputSize = raw["input_size"].asDouble().toInt()
            return Charset(
                unicodeVersion = raw["unicode_version"].asString(),
                inputSize = inputSize,
                embeddingDim = raw["embedding_dim"].asDouble().toInt(),
                rasterization =
                    RasterizationSettings(
                        imageSize = inputSize,
                        contentFraction = raster["content_fraction"].asDouble(),
                        penWidthFraction = raster["pen_width_fraction"].asDouble(),
                        simplifyTolerancePixels = raster["simplify_tolerance_pixels"].asDouble(),
                    ),
                priorWeight = raw["ranking"].asObject()["prior_weight"].asDouble(),
                keyboardScripts =
                    raw["keyboard_scripts"].asObject().mapValues { (_, scripts) ->
                        scripts.asArray().map { it.asString() }
                    },
                characters = characters,
                attribution = raw["attribution"].asArray().map { it.asString() },
            )
        }
    }
}
