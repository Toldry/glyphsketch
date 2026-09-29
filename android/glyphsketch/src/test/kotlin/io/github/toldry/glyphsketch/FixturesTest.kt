package io.github.toldry.glyphsketch

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.BeforeClass
import org.junit.Test
import java.io.File
import java.util.Base64
import kotlin.math.abs

/** Parity with the Python reference: export/fixtures.json (see docs/export_format.md). */
class FixturesTest {
    private class Case(
        val label: String,
        val strokes: List<Stroke>,
        val image: ByteArray,
        val embedding: List<Double>,
        val topCharacters: List<Int>,
        val topScores: List<Double>,
        val tiles: Map<String, List<List<Int>>>,
    )

    companion object {
        private const val TOLERANCE = 1e-4
        private lateinit var recognizer: Recognizer
        private lateinit var cases: List<Case>

        fun exportDir(): File = File(System.getProperty("glyphsketch.exportDir") ?: "../../export")

        @BeforeClass
        @JvmStatic
        fun load() {
            val dir = exportDir()
            assumeTrue(
                "export/ has no exported files; run the export stage",
                File(dir, "fixtures.json").exists(),
            )
            recognizer = Recognizer.load { File(dir, it).inputStream() }
            val raw = Json.parse(File(dir, "fixtures.json").readText()).asObject()
            cases =
                raw["cases"].asArray().map { item ->
                    val case = item.asObject()
                    Case(
                        label = case["label"].asString(),
                        strokes =
                            case["strokes"].asArray().map { stroke ->
                                stroke.asArray().map { point ->
                                    val xy = point.asArray()
                                    Point(xy[0].asDouble(), xy[1].asDouble())
                                }
                            },
                        image = Base64.getDecoder().decode(case["image_uint8_base64"].asString()),
                        embedding = case["embedding"].asArray().map { it.asDouble() },
                        topCharacters =
                            case["top_characters"].asArray().map {
                                it.asDouble().toInt()
                            },
                        topScores = case["top_scores"].asArray().map { it.asDouble() },
                        tiles =
                            case["tiles"].asObject().mapValues { (_, tiles) ->
                                tiles.asArray().map { tile ->
                                    tile.asObject()["members"].asArray().map {
                                        it.asDouble().toInt()
                                    }
                                }
                            },
                    )
                }
        }
    }

    @Test
    fun imagesMatchWithinOneLevel() {
        for (case in cases) {
            val image = Rasterizer.rasterize(case.strokes, recognizer.charset.rasterization)
            val worst =
                image.indices.maxOf {
                    abs((image[it].toInt() and 0xFF) - (case.image[it].toInt() and 0xFF))
                }
            assertTrue("${case.label}: image differs by $worst", worst <= 1)
        }
    }

    @Test
    fun embeddingsMatch() {
        for (case in cases) {
            // From the expected image, so a one-level pixel difference can't mask a model bug.
            val embedding = recognizer.model.embed(case.image)
            case.embedding.forEachIndexed { dim, value ->
                assertTrue(
                    "${case.label}: embedding[$dim]",
                    abs(embedding[dim] - value) < TOLERANCE,
                )
            }
        }
    }

    @Test
    fun rankingsAndScoresMatch() {
        for (case in cases) {
            val ranking =
                recognizer.ranker.rank(
                    recognizer.index.similarities(recognizer.model.embed(case.image)),
                )
            val top = recognizer.ranker.topCharacters(ranking, case.topCharacters.size)
            for ((position, candidate) in top.withIndex()) {
                val expected = case.topCharacters.indexOf(candidate.codePoint)
                assertTrue(
                    "${case.label}: U+${candidate.codePoint.toString(
                        16,
                    )} at $position is unexpected",
                    expected >= 0,
                )
                assertTrue(
                    "${case.label}: score at $position",
                    abs(candidate.score - case.topScores[expected]) < TOLERANCE,
                )
                // Neighbours whose expected scores differ by less than the tolerance may swap.
                if (candidate.codePoint != case.topCharacters[position]) {
                    assertTrue(
                        "${case.label}: position $position",
                        abs(case.topScores[expected] - case.topScores[position]) < TOLERANCE,
                    )
                }
            }
        }
    }

    @Test
    fun tilesMatch() {
        for (case in cases) {
            val ranking =
                recognizer.ranker.rank(
                    recognizer.index.similarities(recognizer.model.embed(case.image)),
                )
            for ((script, expected) in case.tiles) {
                val tiles = recognizer.ranker.tiles(ranking, expected.size, listOf(script))
                assertEquals("${case.label}, $script tiles", expected, tiles.map { it.members })
            }
        }
    }

    @Test
    fun recognizeRunsTheWholePipelineAndTimesIt() {
        val case = cases.first()
        val result = recognizer.recognize(case.strokes, language = "el")
        assertEquals(5, result.tiles.size)
        assertEquals(case.tiles.getValue("Greek")[0], result.tiles[0].members)
        assertTrue(result.timings.totalMs >= result.timings.encodeMs)
    }
}
