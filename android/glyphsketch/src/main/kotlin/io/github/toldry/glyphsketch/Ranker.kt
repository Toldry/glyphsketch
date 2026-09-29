package io.github.toldry.glyphsketch

import java.util.concurrent.ConcurrentHashMap

/** Decides which characters a recognizer may return, e.g. only those the phone can show. */
public typealias CharacterFilter = (CharacterInfo) -> Boolean

/** A ranked character. */
public data class Candidate(
    public val codePoint: Int,
    public val score: Float,
    public val similarity: Float,
)

/** One result tile: a confusable group, shown by its representative. */
public data class Tile(
    public val representative: Int,
    /** The representative first, then the other members in chooser order. */
    public val members: List<Int>,
    public val score: Float,
)

/** Scores of one query and the index columns ordered by them. */
public class Ranking internal constructor(
    public val similarities: FloatArray,
    public val scores: FloatArray,
    public val order: IntArray,
)

/**
 * Ranking and result tiles, as training/src/glyphsketch/ranking.py and web/src/ranking.ts
 * (spec: docs/export_format.md, "Pipeline of one query" and "Tiles"). Thread-safe.
 */
public class Ranker internal constructor(
    public val codePoints: IntArray,
    private val charset: Charset,
) {
    private val weight = charset.priorWeight
    private val infos =
        Array(codePoints.size) { column ->
            charset.characters[codePoints[column]]
                ?: throw IllegalArgumentException(
                    "No metadata for U+${codePoints[column].toString(16)}",
                )
        }
    private val logPriors = FloatArray(codePoints.size) { infos[it].logPrior }
    private val groups = IntArray(codePoints.size) { infos[it].group }
    private val groupColumns: Map<Int, IntArray> =
        codePoints.indices.groupBy { groups[it] }.mapValues { (_, columns) -> columns.toIntArray() }
    private val chooserCache = ConcurrentHashMap<String, List<Int>>()

    internal fun info(column: Int): CharacterInfo = infos[column]

    /** similarity + weight · log prior, per index column. */
    internal fun scores(similarities: FloatArray): FloatArray =
        FloatArray(similarities.size) { (similarities[it] + weight * logPriors[it]).toFloat() }

    /** Columns by decreasing score; ties keep index order. */
    internal fun order(scores: FloatArray): IntArray {
        // Sort (score, column) pairs packed into longs: no boxing, stable on ties.
        val keys =
            LongArray(scores.size) { column ->
                val bits = java.lang.Float.floatToIntBits(scores[column] + 0f) // -0 → +0
                val ordered = if (bits < 0) bits xor 0x7FFFFFFF else bits // monotonic in the score
                (ordered.inv().toLong() shl 32) or column.toLong()
            }
        keys.sort()
        return IntArray(keys.size) { (keys[it] and 0xFFFFFFFFL).toInt() }
    }

    /** Scores and the columns ordered by them: compute once, then take tiles and characters. */
    public fun rank(similarities: FloatArray): Ranking {
        val scores = scores(similarities)
        return Ranking(similarities, scores, order(scores))
    }

    /** The best `count` characters that `accept` lets through (all by default). */
    public fun topCharacters(
        ranking: Ranking,
        count: Int,
        accept: CharacterFilter? = null,
    ): List<Candidate> {
        val result = ArrayList<Candidate>(count)
        for (column in ranking.order) {
            if (result.size == count) break
            if (accept != null && !accept(infos[column])) continue
            result.add(
                Candidate(codePoints[column], ranking.scores[column], ranking.similarities[column]),
            )
        }
        return result
    }

    /** A group's members in code point order. */
    public fun members(group: Int): List<Int> =
        groupColumns[group]?.map { codePoints[it] }?.sorted()
            ?: throw IllegalArgumentException("Unknown group $group")

    /** A group's members for a keyboard typing `scripts`: its representative first. */
    public fun chooser(
        group: Int,
        scripts: List<String>,
    ): List<Int> =
        chooserCache.getOrPut("$group|${scripts.joinToString(",")}") {
            fun typed(column: Int): Boolean =
                infos[column].script in scripts || onEveryKeyboard(infos[column])
            val columns =
                groupColumns.getValue(group).sortedWith(
                    compareBy<Int> { !typed(it) }
                        .thenByDescending { logPriors[it] }
                        .thenBy { codePoints[it] },
                )
            columns.map { codePoints[it] }
        }

    /**
     * One tile per look-alike group, best first. With `accept`, rejected characters leave
     * the tiles' menus, and a group scores by its best accepted member.
     */
    public fun tiles(
        ranking: Ranking,
        count: Int,
        scripts: List<String>,
        accept: CharacterFilter? = null,
    ): List<Tile> {
        val tiles = ArrayList<Tile>(count)
        val seen = HashSet<Int>()
        for (column in ranking.order) {
            if (tiles.size == count) break
            if (accept != null && !accept(infos[column])) continue
            val group = groups[column]
            if (!seen.add(group)) continue
            var chooser = chooser(group, scripts)
            if (accept != null) {
                chooser = chooser.filter { accept(charset.characters.getValue(it)) }
            }
            tiles.add(Tile(chooser[0], chooser, ranking.scores[column]))
        }
        return tiles
    }

    public companion object {
        private val SCRIPTS_ON_EVERY_KEYBOARD = setOf("Common", "Inherited")

        /** Digits, punctuation and symbols are on every keyboard; letters of script
         * Common (𝐚) are not. */
        public fun onEveryKeyboard(info: CharacterInfo): Boolean =
            info.script in SCRIPTS_ON_EVERY_KEYBOARD && !info.generalCategory.startsWith("L")
    }
}
