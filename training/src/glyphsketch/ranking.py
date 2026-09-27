"""Ranking with the frequency prior, and result tiles for confusable groups (M7).

**Score.** ``score(c) = similarity(drawing, c) + weight · log prior(c)``, where the
similarity is the best cosine similarity over the character's index vectors and the prior
comes from the ``wikiprior`` stage. The weight is tuned on real drawings the encoder never
saw (``model.ranking_eval``).

**Tiles.** Members of a confusable group look the same once drawn (Latin A, Greek Α,
Cyrillic А), so results are shown as one tile per group, in the order of each group's best
score. A tile shows one representative and offers the others (for example on long press).
The representative is the most frequent member that the keyboard types: one in a script
of the keyboard's language, or a digit or symbol (script Common), which every keyboard
types (letters of script Common, such as 𝐚, don't count). Without such a member, it is
the most frequent member overall. The ranking is
plain array arithmetic, so the TypeScript and Kotlin engines can reproduce it exactly.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from glyphsketch.charset import CharacterRecord

CANDIDATES_PER_TILE = 8
SCRIPTS_ON_EVERY_KEYBOARD = frozenset({"Common", "Inherited"})


def on_every_keyboard(script: str, general_category: str) -> bool:
    """Digits, punctuation and symbols are typed with every keyboard, so they compete with
    the keyboard's letters on frequency alone. Letters of script Common (𝐚, ℵ) are not."""
    return script in SCRIPTS_ON_EVERY_KEYBOARD and not general_category.startswith("L")


@dataclass(frozen=True)
class Tile:
    representative: int
    members: tuple[int, ...]  # representative first, then the chooser's order
    score: float


class Ranker:
    def __init__(
        self,
        code_points: np.ndarray,
        log_prior: dict[int, float],
        weight: float,
        group_of: dict[int, int],
        script_of: dict[int, str],
        typed_everywhere: frozenset[int] = frozenset(),
    ) -> None:
        """``code_points`` are the index's characters, in its column order;
        ``typed_everywhere`` holds those ``on_every_keyboard``."""
        self.code_points = np.asarray(code_points, dtype=np.int64)
        floor = min(log_prior.values()) if log_prior else 0.0
        self.log_prior = np.array(
            [log_prior.get(int(cp), floor) for cp in self.code_points], dtype=np.float32
        )
        self.weight = weight
        self.script_of = script_of
        self.typed_everywhere = typed_everywhere
        self.group_ids = np.array(
            [group_of.get(int(cp), int(cp)) for cp in self.code_points], dtype=np.int64
        )
        members: dict[int, list[int]] = defaultdict(list)
        for column, group in enumerate(self.group_ids.tolist()):
            members[group].append(column)
        self.members = dict(members)
        self._chooser_cache: dict[tuple[int, tuple[str, ...]], tuple[int, ...]] = {}

    def scores(self, similarities: np.ndarray) -> np.ndarray:
        """(queries, characters) similarities → ranking scores."""
        return similarities + self.weight * self.log_prior

    def top_characters(self, similarities: np.ndarray, k: int) -> np.ndarray:
        """(queries, k) code points, best first, by score."""
        return self.code_points[_top_columns(self.scores(similarities), k)]

    def chooser(self, group: int, scripts: tuple[str, ...]) -> tuple[int, ...]:
        """Code points of a group, representative first."""
        key = (group, scripts)
        if key not in self._chooser_cache:

            def typed(code_point: int) -> bool:
                return (
                    self.script_of.get(code_point, "") in scripts
                    or code_point in self.typed_everywhere
                )

            columns = sorted(
                self.members[group],
                key=lambda column: (
                    not typed(int(self.code_points[column])),
                    -self.log_prior[column],
                    int(self.code_points[column]),
                ),
            )
            self._chooser_cache[key] = tuple(int(self.code_points[c]) for c in columns)
        return self._chooser_cache[key]

    def tiles(self, similarities: np.ndarray, count: int, scripts: Sequence[str]) -> list[Tile]:
        """Tiles for one query: ``similarities`` is its row over the index's characters."""
        scores = self.scores(similarities[None, :])[0]
        wanted = tuple(scripts)
        candidates = min(len(scores), count * CANDIDATES_PER_TILE)
        while True:
            columns = _top_columns(scores[None, :], candidates)[0]
            tiles: list[Tile] = []
            seen: set[int] = set()
            for column in columns.tolist():
                group = int(self.group_ids[column])
                if group in seen:
                    continue
                seen.add(group)
                members = self.chooser(group, wanted)
                tiles.append(Tile(members[0], members, float(scores[column])))
                if len(tiles) == count:
                    return tiles
            if candidates == len(scores):
                return tiles
            candidates = min(len(scores), candidates * 4)

    def tile_representatives(
        self, similarities: np.ndarray, count: int, scripts: Sequence[tuple[str, ...]]
    ) -> np.ndarray:
        """(queries, count) representatives of the first tiles; ``scripts`` per query."""
        rows = []
        for row, query_scripts in zip(similarities, scripts, strict=True):
            representatives = [
                tile.representative for tile in self.tiles(row, count, query_scripts)
            ]
            representatives += [-1] * (count - len(representatives))
            rows.append(representatives)
        return np.array(rows, dtype=np.int64)


def _top_columns(scores: np.ndarray, k: int) -> np.ndarray:
    count = min(k, scores.shape[1])
    top = np.argpartition(-scores, count - 1, axis=1)[:, :count]
    order = np.argsort(-np.take_along_axis(scores, top, axis=1), axis=1, kind="stable")
    return np.take_along_axis(top, order, axis=1)


def typed_on_every_keyboard(characters: Sequence[CharacterRecord]) -> frozenset[int]:
    return frozenset(
        record.code_point
        for record in characters
        if on_every_keyboard(record.script, record.general_category)
    )


KEYBOARD_SCRIPTS = ("Latin", "Greek", "Cyrillic", "Hebrew", "Arabic")


def keyboard_scripts_for(code_point: int, script_of: dict[int, str]) -> tuple[str, ...]:
    """Evaluation assumption: the keyboard is in a language of the drawn character's script,
    and a Latin one for symbols and other scripts."""
    script = script_of.get(code_point, "Common")
    return (script,) if script in KEYBOARD_SCRIPTS else ("Latin",)
