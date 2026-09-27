"""Turn a glyph render into pen strokes: skeletonize, trace the skeleton graph, clean up.

1. The render is binarized and thinned to a one-pixel skeleton.
2. The skeleton becomes a graph. End points and junctions are its nodes; adjacent junction
   pixels count as one junction. A diagonal step is ignored when the same move can be made
   through an orthogonal neighbour; otherwise every staircase corner would look like a
   junction.
3. Short spurs (skeleton branches caused by corners and serifs) are pruned.
4. At every junction the two branches that continue each other most straightly are joined,
   so a "T" becomes two strokes (the bar and the stem), the way people draw it.

Large filled shapes (■ ● ★ ♥ ⬅) are the exception: people draw their outline, while their
skeleton would be spokes or a single point. A glyph counts as filled when a sizeable share
of its ink is far from the edge (thick) and the glyph is large on the em square; its
strokes are then the closed contours of the shape. Small round marks such as "." become a
single point, because people tap them.

The result is a list of polylines in render pixel coordinates (x right, y down).
"""

from collections import defaultdict
from dataclasses import dataclass

import numpy as np
from scipy.ndimage import distance_transform_edt
from skimage.measure import find_contours
from skimage.morphology import skeletonize

from glyphsketch.strokes import simplify_stroke

INK_THRESHOLD = 128
SPUR_FRACTION = 0.09
JOIN_MAX_TURN_DEGREES = 50.0
DIRECTION_SAMPLE_PIXELS = 6
SIMPLIFY_TOLERANCE = 0.6
# A pixel is "thick" when it is this far (as a fraction of the render size) from the edge,
# i.e. the local stroke is wider than 16% of the render.
THICK_DISTANCE_FRACTION = 0.08
FILLED_THICK_SHARE = 0.15
FILLED_MIN_EXTENT_EM = 0.3
MIN_CONTOUR_FRACTION = 0.08
# A skeleton this small compared with the ink means the glyph is a blob (a dot).
BLOB_SKELETON_FRACTION = 0.3

Pixel = tuple[int, int]
_ORTHOGONAL = ((-1, 0), (1, 0), (0, -1), (0, 1))
_DIAGONAL = ((-1, -1), (-1, 1), (1, -1), (1, 1))


def skeleton_pixels(render: np.ndarray) -> set[Pixel]:
    skeleton = skeletonize(np.asarray(render) >= INK_THRESHOLD)
    rows, columns = np.nonzero(skeleton)
    return set(zip(rows.tolist(), columns.tolist(), strict=True))


def neighbours(pixel: Pixel, pixels: set[Pixel]) -> list[Pixel]:
    """Skeleton neighbours, without diagonal shortcuts past an orthogonal neighbour."""
    y, x = pixel
    orthogonal = [(y + dy, x + dx) for dy, dx in _ORTHOGONAL if (y + dy, x + dx) in pixels]
    result = list(orthogonal)
    for dy, dx in _DIAGONAL:
        candidate = (y + dy, x + dx)
        if candidate not in pixels:
            continue
        if (y + dy, x) in pixels or (y, x + dx) in pixels:
            continue
        result.append(candidate)
    return result


@dataclass
class SkeletonGraph:
    """Nodes are junction clusters or end points; edges are pixel paths between nodes."""

    node_of_pixel: dict[Pixel, int]
    node_positions: dict[int, tuple[float, float]]
    edges: list[list[Pixel]]
    edge_nodes: list[tuple[int, int]]
    loops: list[list[Pixel]]
    dots: list[Pixel]


def build_graph(pixels: set[Pixel]) -> SkeletonGraph:
    adjacency = {pixel: neighbours(pixel, pixels) for pixel in pixels}
    junction_pixels = {pixel for pixel, adjacent in adjacency.items() if len(adjacent) >= 3}
    end_pixels = {pixel for pixel, adjacent in adjacency.items() if len(adjacent) == 1}
    dots = [pixel for pixel, adjacent in adjacency.items() if not adjacent]

    node_of_pixel: dict[Pixel, int] = {}
    node_positions: dict[int, tuple[float, float]] = {}
    for pixel in sorted(junction_pixels):
        if pixel in node_of_pixel:
            continue
        node = len(node_positions)
        cluster = [pixel]
        node_of_pixel[pixel] = node
        index = 0
        while index < len(cluster):
            for adjacent in adjacency[cluster[index]]:
                if adjacent in junction_pixels and adjacent not in node_of_pixel:
                    node_of_pixel[adjacent] = node
                    cluster.append(adjacent)
            index += 1
        node_positions[node] = (
            float(np.mean([p[0] for p in cluster])),
            float(np.mean([p[1] for p in cluster])),
        )
    for pixel in sorted(end_pixels):
        node = len(node_positions)
        node_of_pixel[pixel] = node
        node_positions[node] = (float(pixel[0]), float(pixel[1]))

    edges: list[list[Pixel]] = []
    edge_nodes: list[tuple[int, int]] = []
    visited_steps: set[tuple[Pixel, Pixel]] = set()
    for start in sorted(node_of_pixel):
        for first_step in adjacency[start]:
            if (start, first_step) in visited_steps:
                continue
            if first_step in node_of_pixel and node_of_pixel[first_step] == node_of_pixel[start]:
                continue
            path = [start, first_step]
            visited_steps.add((start, first_step))
            visited_steps.add((first_step, start))
            previous, current = start, first_step
            while current not in node_of_pixel:
                options = [p for p in adjacency[current] if p != previous]
                if not options:
                    break
                following = options[0]
                visited_steps.add((current, following))
                visited_steps.add((following, current))
                previous, current = current, following
                path.append(current)
            end_node = node_of_pixel.get(current)
            if end_node is None:
                continue
            edges.append(path)
            edge_nodes.append((node_of_pixel[start], end_node))

    on_edges = {pixel for path in edges for pixel in path}
    loops = []
    remaining = {p for p in pixels if p not in on_edges and p not in node_of_pixel and adjacency[p]}
    while remaining:
        start = min(remaining)
        loop = [start]
        remaining.discard(start)
        previous, current = start, start
        while True:
            options = [p for p in adjacency[current] if p != previous and p in remaining]
            if not options:
                break
            previous, current = current, options[0]
            remaining.discard(current)
            loop.append(current)
        loop.append(start)
        loops.append(loop)
    return SkeletonGraph(node_of_pixel, node_positions, edges, edge_nodes, loops, dots)


def _path_length(path: list[Pixel]) -> float:
    points = np.array(path, dtype=np.float64)
    return float(np.hypot(*np.diff(points, axis=0).T).sum()) if len(points) > 1 else 0.0


def prune_spurs(graph: SkeletonGraph, spur_length: float) -> list[tuple[list[Pixel], int, int]]:
    """Drop short branches between an end point and a junction (serifs, corner artefacts).

    All spurs at a junction go at once, as long as a longer branch remains there: a serif
    foot has two spurs on either side of the stem, and removing them one by one would leave
    the second as a hook once the junction had only two branches left.
    """
    edges = [(path, a, b) for path, (a, b) in zip(graph.edges, graph.edge_nodes, strict=True)]
    while True:
        degree: dict[int, int] = defaultdict(int)
        for _, a, b in edges:
            degree[a] += 1
            degree[b] += 1
        spurs_at: dict[int, list[int]] = defaultdict(list)
        for index, (path, a, b) in enumerate(edges):
            if a == b or (degree[a] == 1) == (degree[b] == 1):
                continue
            junction = b if degree[a] == 1 else a
            if degree[junction] >= 3 and _path_length(path) < spur_length:
                spurs_at[junction].append(index)
        removable = {
            index
            for junction, indices in spurs_at.items()
            if degree[junction] > len(indices)
            for index in indices
        }
        if not removable:
            return edges
        edges = [edge for index, edge in enumerate(edges) if index not in removable]


def _direction_away(path: list[Pixel], from_start: bool) -> np.ndarray:
    points = np.array(path if from_start else path[::-1], dtype=np.float64)
    reach = min(len(points) - 1, DIRECTION_SAMPLE_PIXELS)
    vector = points[reach] - points[0]
    norm = float(np.hypot(*vector))
    return vector / norm if norm > 0 else vector


def join_strokes(edges: list[tuple[list[Pixel], int, int]]) -> list[list[Pixel]]:
    """Concatenate edges through nodes: always through a node that joins exactly two edges
    (a corner), and through a junction only for the pairs that continue each other
    within ``JOIN_MAX_TURN_DEGREES``."""
    ends_at: dict[int, list[tuple[int, bool]]] = defaultdict(list)
    for index, (_, a, b) in enumerate(edges):
        ends_at[a].append((index, True))
        ends_at[b].append((index, False))
    partner: dict[tuple[int, bool], tuple[int, bool]] = {}
    max_cosine = -np.cos(np.radians(180.0 - JOIN_MAX_TURN_DEGREES))
    for incident in ends_at.values():
        if len(incident) < 2:
            continue
        if len(incident) == 2 and incident[0][0] != incident[1][0]:
            partner[incident[0]] = incident[1]
            partner[incident[1]] = incident[0]
            continue
        directions = {end: _direction_away(edges[end[0]][0], end[1]) for end in incident}
        candidates = sorted(
            (float(directions[first] @ directions[second]), first, second)
            for i, first in enumerate(incident)
            for second in incident[i + 1 :]
            if first[0] != second[0]
        )
        for cosine, first, second in candidates:
            if cosine > max_cosine:
                break
            if first in partner or second in partner:
                continue
            partner[first] = second
            partner[second] = first

    used: set[int] = set()
    strokes: list[list[Pixel]] = []
    for start_index in range(len(edges)):
        if start_index in used:
            continue
        chain_start = (start_index, True)
        seen = {start_index}
        while chain_start in partner and partner[chain_start][0] not in seen:
            previous_index, previous_at_start = partner[chain_start]
            seen.add(previous_index)
            chain_start = (previous_index, not previous_at_start)
        index, at_start = chain_start
        path: list[Pixel] = []
        while True:
            used.add(index)
            segment = edges[index][0] if at_start else edges[index][0][::-1]
            path.extend(segment if not path else segment[1:])
            exit_end = (index, not at_start)
            if exit_end not in partner or partner[exit_end][0] in used:
                break
            index, entry_at_start = partner[exit_end]
            at_start = entry_at_start
        strokes.append(path)
    return strokes


def _smooth(points: np.ndarray, closed: bool) -> np.ndarray:
    if len(points) < 5:
        return points
    kernel = np.array([1, 2, 3, 2, 1], dtype=np.float64) / 9.0
    padded = (
        np.concatenate([points[-3:-1], points, points[1:3]])
        if closed
        else np.concatenate([points[:1].repeat(2, axis=0), points, points[-1:].repeat(2, axis=0)])
    )
    smoothed = np.stack(
        [np.convolve(padded[:, axis], kernel, mode="valid") for axis in range(2)], axis=1
    )
    if not closed:
        smoothed[0], smoothed[-1] = points[0], points[-1]
    return smoothed


def is_filled_shape(render: np.ndarray, extent_em: float) -> bool:
    """True for a large glyph with a sizeable share of thick, filled ink."""
    if extent_em < FILLED_MIN_EXTENT_EM:
        return False
    ink = np.asarray(render) >= INK_THRESHOLD
    if not ink.any():
        return False
    distance = distance_transform_edt(ink)
    thick = distance > THICK_DISTANCE_FRACTION * render.shape[0]
    return bool(thick.sum() >= FILLED_THICK_SHARE * ink.sum())


def is_blob(pixels: set[Pixel], render: np.ndarray) -> bool:
    """True when the skeleton is tiny compared with the ink, as for a round dot: the
    skeleton of a disk is a speck that normalization would blow up into a line."""
    rows, columns = np.nonzero(np.asarray(render) >= INK_THRESHOLD)
    ink_extent = max(np.ptp(rows), np.ptp(columns)) + 1
    skeleton = np.array(sorted(pixels))
    skeleton_extent = max(np.ptp(skeleton[:, 0]), np.ptp(skeleton[:, 1])) + 1
    return bool(skeleton_extent < BLOB_SKELETON_FRACTION * ink_extent)


def outline_strokes(render: np.ndarray) -> list[np.ndarray]:
    """Closed contours of the ink, longest first; very short contours are dropped."""
    ink = (np.asarray(render) >= INK_THRESHOLD).astype(np.float64)
    padded = np.pad(ink, 1)
    minimum_length = MIN_CONTOUR_FRACTION * render.shape[0]
    strokes = []
    for contour in find_contours(padded, 0.5):
        points = contour[:, ::-1] - 1.0
        length = float(np.hypot(*np.diff(points, axis=0).T).sum())
        if length >= minimum_length:
            strokes.append((length, simplify_stroke(points, SIMPLIFY_TOLERANCE)))
    return [stroke for _, stroke in sorted(strokes, key=lambda item: -item[0])]


def glyph_strokes(render: np.ndarray, extent_em: float = 1.0) -> list[np.ndarray]:
    """Pen strokes of a glyph render, as float (x, y) polylines in render pixels.

    ``extent_em`` is the longer side of the glyph's ink box in em units; it separates
    large filled shapes (drawn as outlines) from small marks.
    """
    if is_filled_shape(render, extent_em):
        outlines = outline_strokes(render)
        if outlines:
            return outlines
    pixels = skeleton_pixels(render)
    if not pixels:
        return []
    if is_blob(pixels, render):
        rows, columns = np.nonzero(np.asarray(render) >= INK_THRESHOLD)
        return [np.array([[columns.mean(), rows.mean()]], dtype=np.float64)]
    graph = build_graph(pixels)
    spur_length = SPUR_FRACTION * render.shape[0]
    strokes: list[np.ndarray] = []
    for path in join_strokes(prune_spurs(graph, spur_length)):
        points = np.array([(x, y) for y, x in path], dtype=np.float64)
        closed = len(path) > 2 and path[0] == path[-1]
        strokes.append(simplify_stroke(_smooth(points, closed), SIMPLIFY_TOLERANCE))
    for loop in graph.loops:
        points = np.array([(x, y) for y, x in loop], dtype=np.float64)
        strokes.append(simplify_stroke(_smooth(points, True), SIMPLIFY_TOLERANCE))
    for y, x in graph.dots:
        strokes.append(np.array([[x, y]], dtype=np.float64))
    return strokes
