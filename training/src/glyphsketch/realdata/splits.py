"""Deterministic splits of the real data.

* **Test split, by writer.** A writer (Omniglot drawer, UJI writer, or Detexify day) lands
  in the test split when a hash of ``dataset:writer`` falls below ``TEST_FRACTION``. All of
  a writer's samples are on the same side, so test drawings come from people the model
  has not seen.
* **Zero-shot characters.** A hash of the code point puts ``ZERO_SHOT_FRACTION`` of the
  characters with real data into the zero-shot set. Training never sees real drawings of
  these characters (only synthetic ones), so their test accuracy measures how well the
  model generalizes to characters that have no handwriting data, which is the point of the
  design. EVAL.md reports them separately.

Hashing (instead of shuffling with a seed) keeps every assignment stable when datasets are
added or re-downloaded.
"""

import hashlib

import numpy as np

from glyphsketch.realdata.samples import SampleSet

TEST_FRACTION = 0.2
ZERO_SHOT_FRACTION = 0.25


def stable_fraction(text: str) -> float:
    """A number in [0, 1) derived from ``text``, identical on every machine and run."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def is_test_writer(dataset: str, writer: str) -> bool:
    return stable_fraction(f"test-split:{dataset}:{writer}") < TEST_FRACTION


def is_zero_shot_character(code_point: int) -> bool:
    return stable_fraction(f"zero-shot:{code_point:X}") < ZERO_SHOT_FRACTION


def held_out_mask(samples: SampleSet) -> np.ndarray:
    pairs = {(str(d), str(w)) for d, w in zip(samples.datasets, samples.writers, strict=True)}
    test_pairs = {pair for pair in pairs if is_test_writer(*pair)}
    return np.array(
        [
            (str(dataset), str(writer)) in test_pairs
            for dataset, writer in zip(samples.datasets, samples.writers, strict=True)
        ],
        dtype=bool,
    )


def zero_shot_mask(samples: SampleSet) -> np.ndarray:
    zero_shot = {cp for cp in set(samples.code_points.tolist()) if is_zero_shot_character(cp)}
    return np.isin(samples.code_points, list(zero_shot))


def training_mask(samples: SampleSet) -> np.ndarray:
    """Samples that training may use: train-split writers and non-zero-shot characters."""
    mask: np.ndarray = ~held_out_mask(samples) & ~zero_shot_mask(samples)
    return mask
