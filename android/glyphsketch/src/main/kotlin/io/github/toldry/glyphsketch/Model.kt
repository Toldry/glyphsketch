package io.github.toldry.glyphsketch

import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.max
import kotlin.math.sqrt

/** One operation of glyphsketch-model.bin (spec: docs/export_format.md). */
internal sealed interface Operation {
    /** Dense (groups = 1) or depthwise (groups = channels) convolution, "same" padding. */
    class Conv(
        val inChannels: Int,
        val outChannels: Int,
        val kernel: Int,
        val stride: Int,
        val groups: Int,
        val relu6: Boolean,
        /** Dequantized, [out][in / groups][ky][kx]. */
        val weight: FloatArray,
        val bias: FloatArray,
    ) : Operation

    data object ResidualBegin : Operation

    data object ResidualAdd : Operation

    data object GlobalAveragePool : Operation

    class Linear(
        val inFeatures: Int,
        val outFeatures: Int,
        val weight: FloatArray,
        val bias: FloatArray,
    ) : Operation

    data object L2Normalize : Operation
}

/**
 * The encoder: reads glyphsketch-model.bin and runs it in float32, as web/src/model.ts.
 * Weights are dequantized once at load. Instances are immutable and thread-safe.
 */
public class Model internal constructor(
    public val inputSize: Int,
    public val embeddingDim: Int,
    internal val operations: List<Operation>,
) {
    /** Embedding of one image: pixels 0–255 (ink = 255, bytes read unsigned), row-major. */
    public fun embed(image: ByteArray): FloatArray {
        require(image.size == inputSize * inputSize) { "Expected a $inputSize×$inputSize image" }
        var tensor =
            Tensor(
                1,
                inputSize,
                FloatArray(image.size) {
                    (image[it].toInt() and 0xFF) /
                        255f
                },
            )
        var vector: FloatArray? = null
        val saved = ArrayList<Tensor>()
        for (operation in operations) {
            when (operation) {
                is Operation.Conv -> {
                    tensor = convolve(tensor, operation)
                }

                Operation.ResidualBegin -> {
                    saved.add(tensor)
                }

                Operation.ResidualAdd -> {
                    val other = saved.removeAt(saved.size - 1)
                    val sum = FloatArray(tensor.data.size) { tensor.data[it] + other.data[it] }
                    tensor = Tensor(tensor.channels, tensor.size, sum)
                }

                Operation.GlobalAveragePool -> {
                    val pixels = tensor.size * tensor.size
                    vector =
                        FloatArray(tensor.channels) { channel ->
                            var sum = 0f
                            for (pixel in 0 until pixels) {
                                sum +=
                                    tensor.data[channel * pixels + pixel]
                            }
                            sum / pixels
                        }
                }

                is Operation.Linear -> {
                    val input = checkNotNull(vector) { "Linear before pooling" }
                    vector =
                        FloatArray(operation.outFeatures) { out ->
                            var sum = operation.bias[out]
                            val row = out * operation.inFeatures
                            for (feature in 0 until operation.inFeatures) {
                                sum += operation.weight[row + feature] * input[feature]
                            }
                            sum
                        }
                }

                Operation.L2Normalize -> {
                    val input = checkNotNull(vector) { "Normalize before pooling" }
                    var norm = 0f
                    for (value in input) norm += value * value
                    val length = max(sqrt(norm), 1e-12f)
                    vector = FloatArray(input.size) { input[it] / length }
                }
            }
        }
        return checkNotNull(vector) { "The model has no pooling layer" }
    }

    private fun convolve(
        input: Tensor,
        operation: Operation.Conv,
    ): Tensor {
        val outSize = (input.size + operation.stride - 1) / operation.stride
        val outPixels = outSize * outSize
        val output = FloatArray(operation.outChannels * outPixels)
        when {
            operation.kernel == 1 && operation.stride == 1 && operation.groups == 1 -> {
                pointwise(input.data, input.channels, operation, outPixels, output)
            }

            operation.groups == 1 -> {
                dense(input, operation, outSize, output)
            }

            else -> {
                depthwise(input, operation, outSize, output)
            }
        }
        if (operation.relu6) {
            for (index in output.indices) {
                val value = output[index]
                output[index] =
                    if (value < 0f) {
                        0f
                    } else if (value > 6f) {
                        6f
                    } else {
                        value
                    }
            }
        }
        return Tensor(operation.outChannels, outSize, output)
    }

    public companion object {
        private const val MAGIC = "GSKM"
        private const val FORMAT_VERSION = 1

        public fun read(bytes: ByteArray): Model {
            val reader = BinaryReader(bytes)
            reader.checkMagic(MAGIC, "model")
            val version = reader.u16()
            require(version == FORMAT_VERSION) { "Unsupported model format version $version" }
            val inputSize = reader.u16()
            val embeddingDim = reader.u16()
            val count = reader.u16()
            val operations = ArrayList<Operation>(count)
            repeat(count) {
                operations.add(
                    when (val kind = reader.u8()) {
                        1 -> readConv(reader)
                        2 -> Operation.ResidualBegin
                        3 -> Operation.ResidualAdd
                        4 -> Operation.GlobalAveragePool
                        5 -> readLinear(reader)
                        6 -> Operation.L2Normalize
                        else -> throw IllegalArgumentException("Unknown operation kind $kind")
                    },
                )
            }
            require(reader.atEnd()) { "Trailing bytes after the last operation" }
            return Model(inputSize, embeddingDim, operations)
        }

        private fun readConv(reader: BinaryReader): Operation.Conv {
            val inChannels = reader.u16()
            val outChannels = reader.u16()
            val kernel = reader.u8()
            val stride = reader.u8()
            val groups = reader.u16()
            val relu6 = reader.u8() == 1
            reader.align()
            require(groups == 1 || (groups == inChannels && groups == outChannels)) {
                "Only dense and depthwise convolutions are supported"
            }
            val (weight, bias) =
                readQuantized(
                    reader,
                    outChannels,
                    inChannels / groups * kernel * kernel,
                )
            return Operation.Conv(
                inChannels,
                outChannels,
                kernel,
                stride,
                groups,
                relu6,
                weight,
                bias,
            )
        }

        private fun readLinear(reader: BinaryReader): Operation.Linear {
            val inFeatures = reader.u16()
            val outFeatures = reader.u16()
            reader.align()
            val (weight, bias) = readQuantized(reader, outFeatures, inFeatures)
            return Operation.Linear(inFeatures, outFeatures, weight, bias)
        }

        private fun readQuantized(
            reader: BinaryReader,
            outputs: Int,
            perOutput: Int,
        ): Pair<FloatArray, FloatArray> {
            val values = reader.int8(outputs * perOutput)
            reader.align()
            val scales = reader.float32(outputs)
            val bias = reader.float32(outputs)
            val weight = FloatArray(outputs * perOutput) { values[it] * scales[it / perOutput] }
            return weight to bias
        }
    }
}

internal class Tensor(
    val channels: Int,
    val size: Int,
    val data: FloatArray,
)

/**
 * 1×1 convolution, most of the work: output[o][p] = bias[o] + Σ_c weight[o][c] · input[c][p].
 * Blocked 4 outputs × 4 inputs, so every loaded input value feeds four accumulators.
 */
private fun pointwise(
    source: FloatArray,
    inChannels: Int,
    operation: Operation.Conv,
    pixels: Int,
    output: FloatArray,
) {
    val weight = operation.weight
    val outChannels = operation.outChannels
    for (out in 0 until outChannels) {
        output.fill(
            operation.bias[out],
            out * pixels,
            (out + 1) * pixels,
        )
    }
    var out = 0
    while (out + 4 <= outChannels) {
        val t0 = out * pixels
        val t1 = t0 + pixels
        val t2 = t1 + pixels
        val t3 = t2 + pixels
        val w0 = out * inChannels
        val w1 = w0 + inChannels
        val w2 = w1 + inChannels
        val w3 = w2 + inChannels
        var channel = 0
        while (channel + 4 <= inChannels) {
            val s0 = channel * pixels
            val s1 = s0 + pixels
            val s2 = s1 + pixels
            val s3 = s2 + pixels
            val a0 = weight[w0 + channel]
            val a1 = weight[w0 + channel + 1]
            val a2 = weight[w0 + channel + 2]
            val a3 = weight[w0 + channel + 3]
            val b0 = weight[w1 + channel]
            val b1 = weight[w1 + channel + 1]
            val b2 = weight[w1 + channel + 2]
            val b3 = weight[w1 + channel + 3]
            val c0 = weight[w2 + channel]
            val c1 = weight[w2 + channel + 1]
            val c2 = weight[w2 + channel + 2]
            val c3 = weight[w2 + channel + 3]
            val d0 = weight[w3 + channel]
            val d1 = weight[w3 + channel + 1]
            val d2 = weight[w3 + channel + 2]
            val d3 = weight[w3 + channel + 3]
            for (pixel in 0 until pixels) {
                val x0 = source[s0 + pixel]
                val x1 = source[s1 + pixel]
                val x2 = source[s2 + pixel]
                val x3 = source[s3 + pixel]
                output[t0 + pixel] += a0 * x0 + a1 * x1 + a2 * x2 + a3 * x3
                output[t1 + pixel] += b0 * x0 + b1 * x1 + b2 * x2 + b3 * x3
                output[t2 + pixel] += c0 * x0 + c1 * x1 + c2 * x2 + c3 * x3
                output[t3 + pixel] += d0 * x0 + d1 * x1 + d2 * x2 + d3 * x3
            }
            channel += 4
        }
        while (channel < inChannels) {
            val from = channel * pixels
            val a = weight[w0 + channel]
            val b = weight[w1 + channel]
            val c = weight[w2 + channel]
            val d = weight[w3 + channel]
            for (pixel in 0 until pixels) {
                val x = source[from + pixel]
                output[t0 + pixel] += a * x
                output[t1 + pixel] += b * x
                output[t2 + pixel] += c * x
                output[t3 + pixel] += d * x
            }
            channel++
        }
        out += 4
    }
    while (out < outChannels) {
        val target = out * pixels
        for (channel in 0 until inChannels) {
            val w = weight[out * inChannels + channel]
            val from = channel * pixels
            for (pixel in 0 until pixels) output[target + pixel] += w * source[from + pixel]
        }
        out++
    }
}

/** A dense k×k convolution: only the stem, on one input channel. */
private fun dense(
    input: Tensor,
    operation: Operation.Conv,
    outSize: Int,
    output: FloatArray,
) {
    val kernel = operation.kernel
    val stride = operation.stride
    val pad = kernel / 2
    val inSize = input.size
    val inChannels = input.channels
    val source = input.data
    val weight = operation.weight
    val outPixels = outSize * outSize
    for (out in 0 until operation.outChannels) {
        for (row in 0 until outSize) {
            for (column in 0 until outSize) {
                var sum = operation.bias[out]
                for (channel in 0 until inChannels) {
                    for (ky in 0 until kernel) {
                        val y = row * stride + ky - pad
                        if (y < 0 || y >= inSize) continue
                        for (kx in 0 until kernel) {
                            val x = column * stride + kx - pad
                            if (x < 0 || x >= inSize) continue
                            sum +=
                                weight[((out * inChannels + channel) * kernel + ky) * kernel + kx] *
                                source[(channel * inSize + y) * inSize + x]
                        }
                    }
                }
                output[out * outPixels + row * outSize + column] = sum
            }
        }
    }
}

/** Depthwise convolution; interior pixels skip the bounds checks. */
private fun depthwise(
    input: Tensor,
    operation: Operation.Conv,
    outSize: Int,
    output: FloatArray,
) {
    val kernel = operation.kernel
    val stride = operation.stride
    val pad = kernel / 2
    val taps = kernel * kernel
    val inSize = input.size
    val source = input.data
    val weight = operation.weight
    // Output rows/columns whose whole window lies inside the input.
    val first = (pad + stride - 1) / stride
    val last = Math.floorDiv(inSize - kernel + pad, stride)
    for (channel in 0 until operation.outChannels) {
        val base = channel * inSize * inSize
        val target = channel * outSize * outSize
        val w = channel * taps
        val b = operation.bias[channel]
        for (row in 0 until outSize) {
            val interiorRow = row in first..last
            for (column in 0 until outSize) {
                var sum = b
                if (interiorRow && column >= first && column <= last) {
                    var origin = base + (row * stride - pad) * inSize + (column * stride - pad)
                    for (ky in 0 until kernel) {
                        for (kx in 0 until kernel) {
                            sum +=
                                weight[w + ky * kernel + kx] * source[origin + kx]
                        }
                        origin += inSize
                    }
                } else {
                    for (ky in 0 until kernel) {
                        val y = row * stride + ky - pad
                        if (y < 0 || y >= inSize) continue
                        for (kx in 0 until kernel) {
                            val x = column * stride + kx - pad
                            if (x < 0 || x >= inSize) continue
                            sum += weight[w + ky * kernel + kx] * source[base + y * inSize + x]
                        }
                    }
                }
                output[target + row * outSize + column] = sum
            }
        }
    }
}

/** Little-endian reader shared by the model and index formats. */
internal class BinaryReader(
    private val bytes: ByteArray,
) {
    private val buffer: ByteBuffer = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)

    val position: Int get() = buffer.position()

    fun atEnd(): Boolean = !buffer.hasRemaining()

    fun checkMagic(
        magic: String,
        what: String,
    ) {
        val found = String(ByteArray(4) { buffer.get() }, Charsets.US_ASCII)
        require(found == magic) { "Not a glyphsketch $what file" }
    }

    fun u8(): Int = buffer.get().toInt() and 0xFF

    fun u16(): Int = buffer.short.toInt() and 0xFFFF

    fun u32(): Int {
        val value = buffer.int
        require(value >= 0) { "Count too large" }
        return value
    }

    fun align() {
        buffer.position(buffer.position() + (4 - buffer.position() % 4) % 4)
    }

    fun int8(count: Int): ByteArray {
        val values = bytes.copyOfRange(buffer.position(), buffer.position() + count)
        buffer.position(buffer.position() + count)
        return values
    }

    fun float32(count: Int): FloatArray {
        require(
            buffer.position() % 4 == 0,
        ) { "Unaligned float32 array at byte ${buffer.position()}" }
        val values = FloatArray(count)
        buffer.asFloatBuffer().get(values)
        buffer.position(buffer.position() + 4 * count)
        return values
    }

    fun u32Array(count: Int): IntArray {
        val values = IntArray(count)
        buffer.asIntBuffer().get(values)
        buffer.position(buffer.position() + 4 * count)
        return values
    }
}
