package io.github.toldry.glyphsketch.benchmark

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import android.app.Activity
import android.os.Build
import android.os.Bundle
import android.util.Log
import android.view.WindowManager
import android.widget.ScrollView
import android.widget.TextView
import io.github.toldry.glyphsketch.Point
import io.github.toldry.glyphsketch.Rasterizer
import io.github.toldry.glyphsketch.Recognizer
import io.github.toldry.glyphsketch.Stroke
import io.github.toldry.glyphsketch.fromAssets
import org.json.JSONArray
import org.json.JSONObject
import java.nio.FloatBuffer
import kotlin.math.abs
import kotlin.math.max

/**
 * Times the pure-Kotlin encoder against ONNX Runtime (1 and 4 threads) on the parity
 * fixtures' drawings, and the whole Kotlin query. Results go to the screen and to logcat
 * (tag `GlyphsketchBench`, one JSON line): `adb logcat -s GlyphsketchBench`.
 */
class BenchmarkActivity : Activity() {
    private lateinit var output: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        output = TextView(this).apply { setPadding(32, 32, 32, 32) }
        setContentView(ScrollView(this).apply { addView(output) })
        show("Running…")
        Thread {
            val report =
                try {
                    run()
                } catch (error: Throwable) {
                    Log.e(TAG, "Benchmark failed", error)
                    JSONObject().put("error", error.toString())
                }
            Log.i(TAG, report.toString())
            show(report.toString(1))
        }.start()
    }

    private fun show(text: String) = runOnUiThread { output.text = text }

    private fun run(): JSONObject {
        val loadStart = System.nanoTime()
        val recognizer = Recognizer.fromAssets(this)
        val loadMs = (System.nanoTime() - loadStart) / 1e6
        val drawings = fixtureDrawings()
        val images = drawings.map { Rasterizer.rasterize(it, recognizer.charset.rasterization) }
        show("Loaded in %.0f ms; timing the Kotlin engine…".format(loadMs))

        val kotlinEmbeddings = images.map { recognizer.model.embed(it) }
        val kotlinEncode = time(images) { recognizer.model.embed(it) }
        val kotlinQuery = time(drawings) { recognizer.recognize(it) }

        val environment = OrtEnvironment.getEnvironment()
        val modelBytes = assets.open(ONNX_FILE).use { it.readBytes() }
        val onnx = JSONObject()
        for (threads in listOf(1, 4)) {
            show("Timing ONNX Runtime, $threads thread(s)…")
            val options =
                OrtSession.SessionOptions().apply {
                    setIntraOpNumThreads(threads)
                    setOptimizationLevel(OrtSession.SessionOptions.OptLevel.ALL_OPT)
                }
            val sessionStart = System.nanoTime()
            val session = environment.createSession(modelBytes, options)
            val sessionMs = (System.nanoTime() - sessionStart) / 1e6

            fun embed(image: ByteArray): FloatArray {
                val pixels = FloatArray(image.size) { (image[it].toInt() and 0xFF) / 255f }
                val shape = longArrayOf(1, 1, 64, 64)
                OnnxTensor.createTensor(environment, FloatBuffer.wrap(pixels), shape).use { input ->
                    session.run(mapOf("image" to input)).use { result ->
                        @Suppress("UNCHECKED_CAST")
                        return (result[0].value as Array<FloatArray>)[0]
                    }
                }
            }
            var deviation = 0.0
            images.forEachIndexed { case, image ->
                val embedding = embed(image)
                for (dim in embedding.indices) {
                    deviation =
                        max(deviation, abs(embedding[dim] - kotlinEmbeddings[case][dim]).toDouble())
                }
            }
            onnx.put(
                "threads_$threads",
                time(images) { embed(it) }
                    .put("session_ms", sessionMs)
                    .put("max_deviation_from_kotlin", deviation),
            )
            session.close()
        }

        return JSONObject()
            .put("device", "${Build.MANUFACTURER} ${Build.MODEL}")
            .put("soc", if (Build.VERSION.SDK_INT >= 31) Build.SOC_MODEL else "unknown")
            .put("android", Build.VERSION.RELEASE)
            .put("drawings", drawings.size)
            .put("rounds", ROUNDS)
            .put("load_ms", loadMs)
            .put("kotlin_encode", kotlinEncode)
            .put("kotlin_query", kotlinQuery)
            .put("onnxruntime_encode", onnx)
    }

    /** Median and 90th percentile over ROUNDS passes through the inputs, after warming up. */
    private fun <T> time(
        inputs: List<T>,
        work: (T) -> Unit,
    ): JSONObject {
        repeat(WARMUP_ROUNDS) { inputs.forEach(work) }
        val milliseconds = ArrayList<Double>()
        repeat(ROUNDS) {
            for (input in inputs) {
                val start = System.nanoTime()
                work(input)
                milliseconds.add((System.nanoTime() - start) / 1e6)
            }
        }
        milliseconds.sort()

        fun percentile(fraction: Double) =
            milliseconds[((milliseconds.size - 1) * fraction).toInt()]
        return JSONObject()
            .put("median_ms", percentile(0.5))
            .put("p90_ms", percentile(0.9))
            .put("min_ms", milliseconds.first())
    }

    private fun fixtureDrawings(): List<List<Stroke>> {
        val cases =
            JSONObject(assets.open(FIXTURES_FILE).use { it.readBytes().toString(Charsets.UTF_8) })
                .getJSONArray("cases")
        return (0 until cases.length()).map { case ->
            val strokes = cases.getJSONObject(case).getJSONArray("strokes")
            (0 until strokes.length()).map { stroke -> points(strokes.getJSONArray(stroke)) }
        }
    }

    private fun points(stroke: JSONArray): Stroke =
        (0 until stroke.length()).map {
            val point = stroke.getJSONArray(it)
            Point(point.getDouble(0), point.getDouble(1))
        }

    companion object {
        private const val TAG = "GlyphsketchBench"
        private const val ONNX_FILE = "glyphsketch.onnx"
        private const val FIXTURES_FILE = "fixtures.json"
        private const val WARMUP_ROUNDS = 3
        private const val ROUNDS = 10
    }
}
