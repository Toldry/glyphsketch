package io.github.toldry.glyphsketch

import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt

/** A point: x to the right, y down, any unit. */
public data class Point(
    public val x: Double,
    public val y: Double,
)

/** A pen stroke; a single point is a tap and is drawn as a dot. */
public typealias Stroke = List<Point>

public data class RasterizationSettings(
    public val imageSize: Int = 64,
    public val contentFraction: Double = 0.875,
    public val penWidthFraction: Double = 2.5 / 64,
    public val simplifyTolerancePixels: Double = 0.25,
)

/**
 * Strokes → the encoder's 64×64 input image, exactly as training/src/glyphsketch/strokes.py
 * and web/src/rasterize.ts (spec: docs/export_format.md, "Rasterization"). Computed in
 * double precision; the final scaling to bytes repeats NumPy's float32 multiply and
 * round-half-to-even.
 */
public object Rasterizer {
    /** Bytes, row-major, 0 paper to 255 ink. */
    public fun rasterize(
        strokes: List<Stroke>,
        settings: RasterizationSettings = RasterizationSettings(),
    ): ByteArray {
        val fitted = fitToImage(strokes, settings)
        val simplified =
            if (settings.simplifyTolerancePixels > 0) {
                fitted.map { simplifyStroke(it, settings.simplifyTolerancePixels) }
            } else {
                fitted
            }
        val penWidth = settings.penWidthFraction * settings.imageSize
        return rasterizeSegments(segmentsOf(simplified), settings.imageSize, penWidth)
    }

    /** Scale and centre the strokes so the longer side of their bounding box spans
     * contentFraction of the image. */
    internal fun fitToImage(
        strokes: List<Stroke>,
        settings: RasterizationSettings,
    ): List<Stroke> {
        val nonEmpty = strokes.filter { it.isNotEmpty() }
        require(nonEmpty.isNotEmpty()) { "A drawing needs at least one point" }
        var minX = Double.POSITIVE_INFINITY
        var minY = Double.POSITIVE_INFINITY
        var maxX = Double.NEGATIVE_INFINITY
        var maxY = Double.NEGATIVE_INFINITY
        for (stroke in nonEmpty) {
            for (point in stroke) {
                minX = min(minX, point.x)
                minY = min(minY, point.y)
                maxX = max(maxX, point.x)
                maxY = max(maxY, point.y)
            }
        }
        val extent = max(maxX - minX, maxY - minY)
        val size = settings.imageSize
        val scale = if (extent > 0) settings.contentFraction * size / extent else 1.0
        val centreX = (minX + maxX) / 2
        val centreY = (minY + maxY) / 2
        return nonEmpty.map { stroke ->
            stroke.map {
                Point(
                    (it.x - centreX) * scale + size / 2.0,
                    (it.y - centreY) * scale + size / 2.0,
                )
            }
        }
    }

    /** Ramer–Douglas–Peucker simplification that keeps both end points. */
    internal fun simplifyStroke(
        points: Stroke,
        tolerance: Double,
    ): Stroke {
        if (points.size <= 2) return points.toList()
        val keep = BooleanArray(points.size)
        keep[0] = true
        keep[points.size - 1] = true
        val pending = ArrayDeque<Pair<Int, Int>>()
        pending.addLast(0 to points.size - 1)
        while (pending.isNotEmpty()) {
            val (start, end) = pending.removeLast()
            if (end <= start + 1) continue
            val a = points[start]
            val b = points[end]
            val dx = b.x - a.x
            val dy = b.y - a.y
            val length = hypot(dx, dy)
            var farthest = -1
            var farthestDistance = -1.0
            for (index in start + 1 until end) {
                val rx = points[index].x - a.x
                val ry = points[index].y - a.y
                val distance = if (length == 0.0) hypot(rx, ry) else abs(dx * ry - dy * rx) / length
                if (distance > farthestDistance) {
                    farthestDistance = distance
                    farthest = index
                }
            }
            if (farthestDistance > tolerance) {
                keep[farthest] = true
                pending.addLast(start to farthest)
                pending.addLast(farthest to end)
            }
        }
        return points.filterIndexed { index, _ -> keep[index] }
    }

    /** Segments as a flat [ax, ay, bx, by, ...] array; a lone point is a zero-length segment. */
    internal fun segmentsOf(strokes: List<Stroke>): DoubleArray {
        val count = strokes.sumOf { if (it.size == 1) 1 else max(it.size - 1, 0) }
        val values = DoubleArray(4 * count)
        var next = 0
        for (stroke in strokes) {
            if (stroke.size == 1) {
                val point = stroke[0]
                values[next++] = point.x
                values[next++] = point.y
                values[next++] = point.x
                values[next++] = point.y
                continue
            }
            for (index in 0 until stroke.size - 1) {
                values[next++] = stroke[index].x
                values[next++] = stroke[index].y
                values[next++] = stroke[index + 1].x
                values[next++] = stroke[index + 1].y
            }
        }
        return values
    }

    /**
     * Anti-aliased, round-capped segments (pixel coordinates) → bytes, 0 paper to 255 ink.
     *
     * A pixel gets ink only within radius + 0.5 of a segment, so each segment visits just the
     * pixels of its bounding box grown by that much. The image is the same as comparing every
     * pixel with every segment: a segment outside the box is too far to change a pixel's ink.
     */
    internal fun rasterizeSegments(
        segments: DoubleArray,
        imageSize: Int,
        penWidth: Double,
    ): ByteArray {
        val radius = penWidth / 2
        val reach = radius + 0.5
        val nearest = DoubleArray(imageSize * imageSize) { Double.POSITIVE_INFINITY }
        for (segment in 0 until segments.size / 4) {
            val ax = segments[4 * segment]
            val ay = segments[4 * segment + 1]
            val bx = segments[4 * segment + 2]
            val by = segments[4 * segment + 3]
            val dx = bx - ax
            val dy = by - ay
            val lengthSquared = dx * dx + dy * dy
            // Pixel centres are at index + 0.5.
            val firstColumn = max(0, floor(min(ax, bx) - reach - 0.5).toInt())
            val lastColumn = min(imageSize - 1, ceil(max(ax, bx) + reach - 0.5).toInt())
            val firstRow = max(0, floor(min(ay, by) - reach - 0.5).toInt())
            val lastRow = min(imageSize - 1, ceil(max(ay, by) + reach - 0.5).toInt())
            for (row in firstRow..lastRow) {
                val py = row + 0.5
                for (column in firstColumn..lastColumn) {
                    val px = column + 0.5
                    var t =
                        if (lengthSquared >
                            0
                        ) {
                            ((px - ax) * dx + (py - ay) * dy) / lengthSquared
                        } else {
                            0.0
                        }
                    t = min(max(t, 0.0), 1.0)
                    val ex = px - (ax + t * dx)
                    val ey = py - (ay + t * dy)
                    val distance = sqrt(ex * ex + ey * ey)
                    val pixel = row * imageSize + column
                    if (distance < nearest[pixel]) nearest[pixel] = distance
                }
            }
        }
        val image = ByteArray(imageSize * imageSize)
        for (pixel in nearest.indices) {
            val ink = min(max(radius + 0.5 - nearest[pixel], 0.0), 1.0)
            image[pixel] = roundHalfEven((ink.toFloat() * 255f).toDouble()).toByte()
        }
        return image
    }

    /** Round half to even, as numpy.round does. */
    private fun roundHalfEven(value: Double): Int {
        val lower = floor(value)
        val difference = value - lower
        val result =
            when {
                difference > 0.5 -> lower + 1
                difference < 0.5 -> lower
                lower % 2 == 0.0 -> lower
                else -> lower + 1
            }
        return result.toInt()
    }
}
