"""Distort clean glyph strokes into plausible hand-drawn strokes.

All operations work on strokes in normalized drawing coordinates (the bounding box is
centered on the origin and its longer side is 1), so the amounts below are fractions of
the drawing size. Every random choice comes from the ``numpy.random.Generator`` passed in,
so a sample is fully determined by its seed.

Order of operations for one sample:

1. resample each stroke at even arc-length spacing;
2. closed loops are usually cut open at a random point;
3. per-stroke jitter: a small shift, rotation and scale around the stroke's centre, so
   strokes no longer meet exactly at junctions;
4. over- and undershoot: each open stroke end is extended or trimmed along its tangent,
   leaving gaps and overlaps where strokes (or the two ends of a loop) should meet;
5. wobble: smooth noise perpendicular to the stroke, like an unsteady hand;
6. corner rounding: Gaussian smoothing along the stroke;
7. a smooth global elastic displacement field;
8. a global affine transform: rotation, shear and a change of aspect ratio.

The pen width is chosen separately when the strokes are rasterized.
"""

from dataclasses import dataclass

import numpy as np

Strokes = list[np.ndarray]


@dataclass(frozen=True)
class AugmentationConfig:
    point_spacing: float = 0.012
    stroke_shift: float = 0.025
    stroke_rotation_degrees: float = 5.0
    stroke_log_scale: float = 0.08
    endpoint_change: float = 0.04
    open_loop_probability: float = 0.6
    wobble_amplitude: float = 0.008
    wobble_wavelength: tuple[float, float] = (0.15, 0.6)
    corner_smoothing: tuple[float, float] = (0.0, 0.025)
    elastic_amplitude: float = 0.035
    elastic_frequency: tuple[float, float] = (0.4, 1.6)
    elastic_components: int = 3
    rotation_degrees: float = 9.0
    shear: float = 0.22
    log_aspect: float = 0.22
    pen_width_fraction: tuple[float, float] = (1.4 / 64, 4.2 / 64)


def normalize_strokes(strokes: Strokes) -> Strokes:
    """Center the bounding box on the origin and scale its longer side to 1."""
    points = np.concatenate(strokes)
    minimum, maximum = points.min(axis=0), points.max(axis=0)
    extent = float(max(maximum - minimum))
    scale = 1.0 / extent if extent > 0 else 1.0
    center = (minimum + maximum) / 2
    return [(np.asarray(stroke, dtype=np.float64) - center) * scale for stroke in strokes]


def resample(stroke: np.ndarray, spacing: float) -> np.ndarray:
    """Points at even arc-length spacing along the stroke (end points kept)."""
    if len(stroke) < 2:
        return stroke
    steps = np.hypot(*np.diff(stroke, axis=0).T)
    arc = np.concatenate([[0.0], np.cumsum(steps)])
    total = arc[-1]
    if total == 0:
        return stroke[:1]
    count = max(2, int(np.ceil(total / spacing)) + 1)
    targets = np.linspace(0.0, total, count)
    return np.stack([np.interp(targets, arc, stroke[:, axis]) for axis in range(2)], axis=1)


def _rotation(degrees: float) -> np.ndarray:
    radians = np.radians(degrees)
    cosine, sine = np.cos(radians), np.sin(radians)
    return np.array([[cosine, -sine], [sine, cosine]])


def jitter_stroke(
    stroke: np.ndarray, config: AugmentationConfig, rng: np.random.Generator
) -> np.ndarray:
    center = stroke.mean(axis=0)
    rotation = _rotation(rng.uniform(-1, 1) * config.stroke_rotation_degrees)
    scale = np.exp(rng.uniform(-1, 1) * config.stroke_log_scale)
    shift = rng.uniform(-1, 1, size=2) * config.stroke_shift
    return (stroke - center) @ rotation.T * scale + center + shift


def _is_closed(stroke: np.ndarray, spacing: float) -> bool:
    return len(stroke) > 3 and float(np.hypot(*(stroke[0] - stroke[-1]))) < 2 * spacing


def open_loop(stroke: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Start a closed loop at a random point and drop the closing point, so that the
    endpoint change can leave a gap or an overlap where the pen meets its start."""
    start = int(rng.integers(len(stroke) - 1))
    return np.concatenate([stroke[start:-1], stroke[: start + 1]])


def change_endpoints(
    stroke: np.ndarray, config: AugmentationConfig, rng: np.random.Generator, spacing: float
) -> np.ndarray:
    """Extend or trim both ends of an open stroke along its tangent."""
    if len(stroke) < 3 or _is_closed(stroke, spacing):
        return stroke
    result = stroke
    for at_start in (True, False):
        change = rng.uniform(-1, 1) * config.endpoint_change
        if change >= 0:
            end, before = (result[0], result[1]) if at_start else (result[-1], result[-2])
            tangent = end - before
            norm = float(np.hypot(*tangent))
            if norm == 0:
                continue
            extra = end + tangent / norm * change
            result = np.vstack([extra, result]) if at_start else np.vstack([result, extra])
        else:
            trim = min(int(-change / spacing), len(result) - 2)
            if trim > 0:
                result = result[trim:] if at_start else result[:-trim]
    return result


def wobble(stroke: np.ndarray, config: AugmentationConfig, rng: np.random.Generator) -> np.ndarray:
    """Displace points perpendicular to the stroke by a smooth random function of arc length."""
    if len(stroke) < 3:
        return stroke
    tangent = np.gradient(stroke, axis=0)
    norms = np.maximum(np.hypot(*tangent.T), 1e-9)
    normal = np.stack([-tangent[:, 1], tangent[:, 0]], axis=1) / norms[:, None]
    arc = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(stroke, axis=0).T))])
    offset = np.zeros(len(stroke))
    for _ in range(2):
        wavelength = rng.uniform(*config.wobble_wavelength)
        phase = rng.uniform(0, 2 * np.pi)
        offset += np.sin(2 * np.pi * arc / wavelength + phase)
    amplitude = rng.uniform(0, config.wobble_amplitude)
    return stroke + normal * (offset * amplitude / 2)[:, None]


def smooth_corners(stroke: np.ndarray, sigma: float, spacing: float, closed: bool) -> np.ndarray:
    """Gaussian smoothing along the stroke; ``sigma`` in drawing units."""
    radius_points = sigma / spacing
    if len(stroke) < 5 or radius_points < 0.5:
        return stroke
    half = int(np.ceil(3 * radius_points))
    offsets = np.arange(-half, half + 1)
    kernel = np.exp(-0.5 * (offsets / radius_points) ** 2)
    kernel /= kernel.sum()
    if closed:
        padded = np.concatenate([stroke[-half - 1 : -1], stroke, stroke[1 : half + 1]])
    else:
        padded = np.concatenate(
            [np.repeat(stroke[:1], half, axis=0), stroke, np.repeat(stroke[-1:], half, axis=0)]
        )
    if len(padded) < len(kernel):
        return stroke
    smoothed = np.stack(
        [np.convolve(padded[:, axis], kernel, mode="valid") for axis in range(2)], axis=1
    )
    if not closed:
        smoothed[0], smoothed[-1] = stroke[0], stroke[-1]
    return smoothed[: len(stroke)]


def elastic_field(
    config: AugmentationConfig, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Random low-frequency sine components: wave vectors (K, 2), phases (K,), amplitudes (K, 2)."""
    count = config.elastic_components
    frequencies = rng.uniform(*config.elastic_frequency, size=count)
    angles = rng.uniform(0, 2 * np.pi, size=count)
    waves = np.stack([np.cos(angles), np.sin(angles)], axis=1) * frequencies[:, None] * 2 * np.pi
    phases = rng.uniform(0, 2 * np.pi, size=count)
    amplitudes = rng.normal(0, 1, size=(count, 2)) * config.elastic_amplitude / np.sqrt(count)
    return waves, phases, amplitudes


def apply_elastic(
    stroke: np.ndarray, field: tuple[np.ndarray, np.ndarray, np.ndarray]
) -> np.ndarray:
    waves, phases, amplitudes = field
    displacement = np.sin(stroke @ waves.T + phases) @ amplitudes
    return stroke + displacement


def global_affine(config: AugmentationConfig, rng: np.random.Generator) -> np.ndarray:
    rotation = _rotation(rng.uniform(-1, 1) * config.rotation_degrees)
    shear = np.array([[1.0, rng.uniform(-1, 1) * config.shear], [0.0, 1.0]])
    aspect = np.exp(rng.uniform(-1, 1) * config.log_aspect)
    scale = np.diag([np.sqrt(aspect), 1 / np.sqrt(aspect)])
    return rotation @ shear @ scale


def augment_strokes(
    strokes: Strokes, config: AugmentationConfig, rng: np.random.Generator
) -> Strokes:
    """One hand-drawn-looking variant of clean glyph strokes (normalized coordinates)."""
    normalized = normalize_strokes(strokes)
    spacing = config.point_spacing
    sigma = rng.uniform(*config.corner_smoothing)
    field = elastic_field(config, rng)
    affine = global_affine(config, rng)
    result = []
    for stroke in normalized:
        if len(stroke) == 1:
            point = stroke + rng.uniform(-1, 1, size=2) * config.stroke_shift
            result.append(apply_elastic(point, field) @ affine.T)
            continue
        closed = _is_closed(stroke, spacing)
        points = resample(stroke, spacing)
        if closed and rng.random() < config.open_loop_probability:
            points = open_loop(points, rng)
            closed = False
        points = jitter_stroke(points, config, rng)
        points = change_endpoints(points, config, rng, spacing)
        points = wobble(points, config, rng)
        points = smooth_corners(points, sigma, spacing, closed)
        points = apply_elastic(points, field)
        result.append(points @ affine.T)
    return result


def pen_width_for(image_size: int, config: AugmentationConfig, rng: np.random.Generator) -> float:
    low, high = config.pen_width_fraction
    return float(np.exp(rng.uniform(np.log(low), np.log(high)))) * image_size
