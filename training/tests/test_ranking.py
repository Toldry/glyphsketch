import numpy as np

from glyphsketch.ranking import Ranker, keyboard_scripts_for

LATIN_A, GREEK_ALPHA, CYRILLIC_A, LATIN_B, RARE = 0x41, 0x391, 0x410, 0x42, 0x2A01
SCRIPT_OF = {
    LATIN_A: "Latin",
    GREEK_ALPHA: "Greek",
    CYRILLIC_A: "Cyrillic",
    LATIN_B: "Latin",
    RARE: "Common",
}
GROUP_OF = {LATIN_A: LATIN_A, GREEK_ALPHA: LATIN_A, CYRILLIC_A: LATIN_A}
LOG_PRIOR = {LATIN_A: -3.0, GREEK_ALPHA: -9.0, CYRILLIC_A: -7.0, LATIN_B: -4.0, RARE: -20.0}
CODE_POINTS = np.array([LATIN_A, GREEK_ALPHA, CYRILLIC_A, LATIN_B, RARE])


def _ranker(weight: float) -> Ranker:
    return Ranker(CODE_POINTS, LOG_PRIOR, weight, GROUP_OF, SCRIPT_OF)


def test_the_prior_breaks_near_ties_in_favour_of_common_characters() -> None:
    similarities = np.array([[0.1, 0.1, 0.1, 0.80, 0.81]], dtype=np.float32)
    assert _ranker(0.0).top_characters(similarities, 2)[0].tolist() == [RARE, LATIN_B]
    assert _ranker(0.01).top_characters(similarities, 2)[0].tolist() == [LATIN_B, RARE]


def test_tiles_merge_a_group_and_pick_the_keyboard_script() -> None:
    similarities = np.array([0.9, 0.95, 0.92, 0.5, 0.1], dtype=np.float32)
    ranker = _ranker(0.0)
    english = ranker.tiles(similarities, 5, ("Latin",))
    assert [tile.representative for tile in english] == [LATIN_A, LATIN_B, RARE]
    assert english[0].members == (LATIN_A, CYRILLIC_A, GREEK_ALPHA)
    assert english[0].score == np.float32(0.95)
    greek = ranker.tiles(similarities, 1, ("Greek",))
    assert greek[0].representative == GREEK_ALPHA
    hebrew = ranker.tiles(similarities, 1, ("Hebrew",))
    assert hebrew[0].representative == LATIN_A  # no member in the script: most frequent


def test_tile_representatives_pad_when_there_are_few_groups() -> None:
    similarities = np.array([[0.9, 0.8, 0.7, 0.6, 0.5]], dtype=np.float32)
    representatives = _ranker(0.0).tile_representatives(similarities, 5, [("Cyrillic",)])
    assert representatives.tolist() == [[CYRILLIC_A, LATIN_B, RARE, -1, -1]]


def test_keyboard_scripts_fall_back_to_latin_for_symbols() -> None:
    assert keyboard_scripts_for(GREEK_ALPHA, SCRIPT_OF) == ("Greek",)
    assert keyboard_scripts_for(RARE, SCRIPT_OF) == ("Latin",)
