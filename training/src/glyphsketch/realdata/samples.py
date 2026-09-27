"""Columnar storage for many labelled drawings.

All points of all strokes live in one float32 array; offsets say where each stroke and
each sample starts. This keeps a few hundred thousand drawings in a single ``.npz`` that
loads in one read.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class DrawingSample:
    dataset: str
    sample_id: str
    writer: str
    label: str
    """The dataset's own label, e.g. a Detexify key or an Omniglot character folder."""
    code_point: int
    strokes: Sequence[np.ndarray] = field(repr=False)


@dataclass(frozen=True)
class SampleSet:
    points: np.ndarray
    stroke_offsets: np.ndarray
    sample_offsets: np.ndarray
    code_points: np.ndarray
    datasets: np.ndarray
    writers: np.ndarray
    labels: np.ndarray
    sample_ids: np.ndarray

    def __len__(self) -> int:
        return len(self.code_points)

    @classmethod
    def from_samples(cls, samples: Iterable[DrawingSample]) -> "SampleSet":
        points: list[np.ndarray] = []
        stroke_offsets = [0]
        sample_offsets = [0]
        code_points: list[int] = []
        datasets: list[str] = []
        writers: list[str] = []
        labels: list[str] = []
        sample_ids: list[str] = []
        for sample in samples:
            for stroke in sample.strokes:
                stroke_array = np.asarray(stroke, dtype=np.float32).reshape(-1, 2)
                points.append(stroke_array)
                stroke_offsets.append(stroke_offsets[-1] + len(stroke_array))
            sample_offsets.append(len(stroke_offsets) - 1)
            code_points.append(sample.code_point)
            datasets.append(sample.dataset)
            writers.append(sample.writer)
            labels.append(sample.label)
            sample_ids.append(sample.sample_id)
        return cls(
            points=np.concatenate(points) if points else np.zeros((0, 2), dtype=np.float32),
            stroke_offsets=np.array(stroke_offsets, dtype=np.int64),
            sample_offsets=np.array(sample_offsets, dtype=np.int64),
            code_points=np.array(code_points, dtype=np.int32),
            datasets=np.array(datasets, dtype=str),
            writers=np.array(writers, dtype=str),
            labels=np.array(labels, dtype=str),
            sample_ids=np.array(sample_ids, dtype=str),
        )

    def strokes(self, index: int) -> list[np.ndarray]:
        first_stroke = self.sample_offsets[index]
        last_stroke = self.sample_offsets[index + 1]
        return [
            self.points[self.stroke_offsets[stroke] : self.stroke_offsets[stroke + 1]]
            for stroke in range(first_stroke, last_stroke)
        ]

    def sample(self, index: int) -> DrawingSample:
        return DrawingSample(
            dataset=str(self.datasets[index]),
            sample_id=str(self.sample_ids[index]),
            writer=str(self.writers[index]),
            label=str(self.labels[index]),
            code_point=int(self.code_points[index]),
            strokes=self.strokes(index),
        )

    def subset(self, indices: Sequence[int] | np.ndarray) -> "SampleSet":
        return SampleSet.from_samples(self.sample(int(index)) for index in indices)

    def save(self, path: Path) -> None:
        np.savez_compressed(
            path,
            points=self.points,
            stroke_offsets=self.stroke_offsets,
            sample_offsets=self.sample_offsets,
            code_points=self.code_points,
            datasets=self.datasets,
            writers=self.writers,
            labels=self.labels,
            sample_ids=self.sample_ids,
        )

    @classmethod
    def load(cls, path: Path) -> "SampleSet":
        with np.load(path, allow_pickle=False) as data:
            return cls(**{name: data[name] for name in data.files})
