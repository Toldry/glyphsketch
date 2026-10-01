/**
 * Strokes → the encoder's 64×64 input image, exactly as training/src/glyphsketch/strokes.py
 * (spec: docs/export_format.md, "Rasterization"). Computed in double precision; the final
 * scaling to bytes repeats NumPy's float32 multiply and round-half-to-even.
 */
export const DEFAULT_RASTERIZATION = {
    imageSize: 64,
    contentFraction: 0.875,
    penWidthFraction: 2.5 / 64,
    simplifyTolerancePixels: 0.25,
};
/** Scale and centre the strokes so the longer side of their bounding box spans
 * contentFraction of the image. */
export function fitToImage(strokes, settings) {
    const nonEmpty = strokes.filter((stroke) => stroke.length > 0);
    if (nonEmpty.length === 0) {
        throw new Error("A drawing needs at least one point");
    }
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const stroke of nonEmpty) {
        for (const [x, y] of stroke) {
            minX = Math.min(minX, x);
            minY = Math.min(minY, y);
            maxX = Math.max(maxX, x);
            maxY = Math.max(maxY, y);
        }
    }
    const extent = Math.max(maxX - minX, maxY - minY);
    const size = settings.imageSize;
    const scale = extent > 0 ? (settings.contentFraction * size) / extent : 1.0;
    const centreX = (minX + maxX) / 2;
    const centreY = (minY + maxY) / 2;
    return nonEmpty.map((stroke) => stroke.map(([x, y]) => [(x - centreX) * scale + size / 2, (y - centreY) * scale + size / 2]));
}
/** Ramer–Douglas–Peucker simplification that keeps both end points. */
export function simplifyStroke(points, tolerance) {
    if (points.length <= 2) {
        return [...points];
    }
    const keep = new Uint8Array(points.length);
    keep[0] = 1;
    keep[points.length - 1] = 1;
    const pending = [[0, points.length - 1]];
    while (pending.length > 0) {
        const [start, end] = pending.pop();
        if (end <= start + 1) {
            continue;
        }
        const [ax, ay] = points[start];
        const [bx, by] = points[end];
        const dx = bx - ax;
        const dy = by - ay;
        const length = Math.hypot(dx, dy);
        let farthest = -1;
        let farthestDistance = -1;
        for (let index = start + 1; index < end; index++) {
            const [px, py] = points[index];
            const rx = px - ax;
            const ry = py - ay;
            const distance = length === 0 ? Math.hypot(rx, ry) : Math.abs(dx * ry - dy * rx) / length;
            if (distance > farthestDistance) {
                farthestDistance = distance;
                farthest = index;
            }
        }
        if (farthestDistance > tolerance) {
            keep[farthest] = 1;
            pending.push([start, farthest], [farthest, end]);
        }
    }
    return points.filter((_, index) => keep[index] === 1);
}
/** Segments as a flat [ax, ay, bx, by, ...] array; a lone point is a zero-length segment. */
export function segmentsOf(strokes) {
    const values = [];
    for (const stroke of strokes) {
        if (stroke.length === 1) {
            const [x, y] = stroke[0];
            values.push(x, y, x, y);
            continue;
        }
        for (let index = 0; index + 1 < stroke.length; index++) {
            const [ax, ay] = stroke[index];
            const [bx, by] = stroke[index + 1];
            values.push(ax, ay, bx, by);
        }
    }
    return Float64Array.from(values);
}
/** Round half to even, as numpy.round does. */
function roundHalfEven(value) {
    const floor = Math.floor(value);
    const difference = value - floor;
    if (difference > 0.5)
        return floor + 1;
    if (difference < 0.5)
        return floor;
    return floor % 2 === 0 ? floor : floor + 1;
}
/**
 * Anti-aliased, round-capped segments (pixel coordinates) → bytes, 0 paper to 255 ink.
 *
 * A pixel gets ink only within radius + 0.5 of a segment, so each segment visits just the
 * pixels of its bounding box grown by that much. The image is the same as comparing every
 * pixel with every segment: a segment outside the box is too far to change a pixel's ink.
 */
export function rasterizeSegments(segments, imageSize, penWidth) {
    const radius = penWidth / 2;
    const reach = radius + 0.5;
    const nearest = new Float64Array(imageSize * imageSize).fill(Infinity);
    for (let segment = 0; segment < segments.length / 4; segment++) {
        const ax = segments[4 * segment];
        const ay = segments[4 * segment + 1];
        const bx = segments[4 * segment + 2];
        const by = segments[4 * segment + 3];
        const dx = bx - ax;
        const dy = by - ay;
        const lengthSquared = dx * dx + dy * dy;
        // Pixel centres are at index + 0.5.
        const firstColumn = Math.max(0, Math.floor(Math.min(ax, bx) - reach - 0.5));
        const lastColumn = Math.min(imageSize - 1, Math.ceil(Math.max(ax, bx) + reach - 0.5));
        const firstRow = Math.max(0, Math.floor(Math.min(ay, by) - reach - 0.5));
        const lastRow = Math.min(imageSize - 1, Math.ceil(Math.max(ay, by) + reach - 0.5));
        for (let row = firstRow; row <= lastRow; row++) {
            const py = row + 0.5;
            for (let column = firstColumn; column <= lastColumn; column++) {
                const px = column + 0.5;
                let t = lengthSquared > 0 ? ((px - ax) * dx + (py - ay) * dy) / lengthSquared : 0;
                t = Math.min(Math.max(t, 0), 1);
                const ex = px - (ax + t * dx);
                const ey = py - (ay + t * dy);
                const distance = Math.sqrt(ex * ex + ey * ey);
                const pixel = row * imageSize + column;
                if (distance < nearest[pixel])
                    nearest[pixel] = distance;
            }
        }
    }
    const image = new Uint8Array(imageSize * imageSize);
    for (let pixel = 0; pixel < nearest.length; pixel++) {
        const ink = Math.min(Math.max(radius + 0.5 - nearest[pixel], 0), 1);
        image[pixel] = roundHalfEven(Math.fround(Math.fround(ink) * 255));
    }
    return image;
}
export function rasterize(strokes, settings = DEFAULT_RASTERIZATION) {
    const fitted = fitToImage(strokes, settings);
    const simplified = settings.simplifyTolerancePixels > 0
        ? fitted.map((stroke) => simplifyStroke(stroke, settings.simplifyTolerancePixels))
        : fitted;
    const penWidth = settings.penWidthFraction * settings.imageSize;
    return rasterizeSegments(segmentsOf(simplified), settings.imageSize, penWidth);
}
//# sourceMappingURL=rasterize.js.map