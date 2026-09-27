"""Pen strokes and their rasterization into the model's input images.

A drawing is a sequence of strokes; a stroke is a float array of shape (n, 2) holding
(x, y) points in any unit, with x to the right and y down (screen convention).

Rasterization frames the drawing exactly like glyph renders (``render.py``): the bounding
box of all points is scaled, keeping its aspect ratio, so that its longer side spans
``CONTENT_FRACTION`` of the image, and centered. Strokes are then drawn as anti-aliased
lines of constant width with round caps and joins, using a distance field: a pixel's ink
is ``clamp(radius + 0.5 - d, 0, 1)``, where ``d`` is the distance from the pixel center
to the nearest segment. The web and Android engines implement the same formula, so a
drawing produces the same input image on every platform.
"""

from collections.abc import Sequence

import numpy as np

from glyphsketch.render import CONTENT_SIZE, IMAGE_SIZE

CONTENT_FRACTION = CONTENT_SIZE / IMAGE_SIZE
DEFAULT_PEN_WIDTH_FRACTION = 2.5 / 64
SEGMENT_CHUNK = 64

Stroke = np.ndarray
Drawing = Sequence[Stroke]


def drawing_bounds(strokes: Drawing) -> tuple[float, float, float, float]:
    """(min x, min y, max x, max y) over all points."""
    points = np.concatenate([np.asarray(stroke, dtype=np.float64) for stroke in strokes])
    minimum = points.min(axis=0)
    maximum = points.max(axis=0)
    return float(minimum[0]), float(minimum[1]), float(maximum[0]), float(maximum[1])


def fit_to_image(strokes: Drawing, image_size: int) -> list[np.ndarray]:
    """Scale and translate the strokes into pixel coordinates of an image_size square."""
    if not strokes or all(len(stroke) == 0 for stroke in strokes):
        raise ValueError("A drawing needs at least one point")
    strokes = [np.asarray(stroke, dtype=np.float64) for stroke in strokes if len(stroke)]
    min_x, min_y, max_x, max_y = drawing_bounds(strokes)
    extent = max(max_x - min_x, max_y - min_y)
    scale = CONTENT_FRACTION * image_size / extent if extent > 0 else 1.0
    center = np.array([(min_x + max_x) / 2, (min_y + max_y) / 2])
    offset = np.array([image_size / 2, image_size / 2])
    return [(stroke - center) * scale + offset for stroke in strokes]


def simplify_stroke(points: np.ndarray, tolerance: float) -> np.ndarray:
    """Ramer-Douglas-Peucker simplification (keeps both end points)."""
    if len(points) <= 2:
        return points
    keep = np.zeros(len(points), dtype=bool)
    keep[0] = keep[-1] = True
    pending = [(0, len(points) - 1)]
    while pending:
        start, end = pending.pop()
        if end <= start + 1:
            continue
        a, b = points[start], points[end]
        direction = b - a
        length = float(np.hypot(*direction))
        inner = points[start + 1 : end]
        relative = inner - a
        if length == 0:
            distances = np.hypot(relative[:, 0], relative[:, 1])
        else:
            cross = direction[0] * relative[:, 1] - direction[1] * relative[:, 0]
            distances = np.abs(cross) / length
        farthest = int(np.argmax(distances))
        if distances[farthest] > tolerance:
            split = start + 1 + farthest
            keep[split] = True
            pending.append((start, split))
            pending.append((split, end))
    return points[keep]


def segments_of(strokes: Sequence[np.ndarray]) -> np.ndarray:
    """All line segments as an (S, 4) array of (ax, ay, bx, by); a lone point is a segment
    of length zero, so taps render as dots."""
    segments = []
    for stroke in strokes:
        if len(stroke) == 1:
            segments.append(np.concatenate([stroke[0], stroke[0]])[None, :])
        else:
            segments.append(np.concatenate([stroke[:-1], stroke[1:]], axis=1))
    return np.concatenate(segments).astype(np.float64)


def rasterize_segments(segments: np.ndarray, image_size: int, pen_width: float) -> np.ndarray:
    """Ink image (float32, 0..1) of anti-aliased round-capped segments in pixel coordinates."""
    radius = pen_width / 2
    centers = np.arange(image_size, dtype=np.float64) + 0.5
    grid_x, grid_y = np.meshgrid(centers, centers)
    pixels_x = grid_x.reshape(-1, 1)
    pixels_y = grid_y.reshape(-1, 1)
    nearest = np.full(image_size * image_size, np.inf)
    for start in range(0, len(segments), SEGMENT_CHUNK):
        chunk = segments[start : start + SEGMENT_CHUNK]
        ax, ay, bx, by = chunk[:, 0], chunk[:, 1], chunk[:, 2], chunk[:, 3]
        dx, dy = bx - ax, by - ay
        length_squared = dx * dx + dy * dy
        safe = np.where(length_squared > 0, length_squared, 1.0)
        t = ((pixels_x - ax) * dx + (pixels_y - ay) * dy) / safe
        t = np.clip(np.where(length_squared > 0, t, 0.0), 0.0, 1.0)
        distance_x = pixels_x - (ax + t * dx)
        distance_y = pixels_y - (ay + t * dy)
        distances = np.sqrt(distance_x * distance_x + distance_y * distance_y)
        nearest = np.minimum(nearest, distances.min(axis=1))
    ink = np.clip(radius + 0.5 - nearest, 0.0, 1.0)
    return ink.reshape(image_size, image_size).astype(np.float32)


def rasterize(
    strokes: Drawing,
    image_size: int = IMAGE_SIZE,
    pen_width: float | None = None,
    simplify_tolerance: float = 0.25,
) -> np.ndarray:
    """Render a drawing as a uint8 image (0 paper, 255 ink), framed like the glyph renders.

    ``pen_width`` is in output pixels and defaults to ``DEFAULT_PEN_WIDTH_FRACTION`` of the
    image size. Strokes are simplified to within ``simplify_tolerance`` output pixels first,
    which changes the image imperceptibly and makes long strokes much cheaper to draw.
    """
    if pen_width is None:
        pen_width = DEFAULT_PEN_WIDTH_FRACTION * image_size
    fitted = fit_to_image(strokes, image_size)
    if simplify_tolerance > 0:
        fitted = [simplify_stroke(stroke, simplify_tolerance) for stroke in fitted]
    ink = rasterize_segments(segments_of(fitted), image_size, pen_width)
    return np.round(ink * 255).astype(np.uint8)
