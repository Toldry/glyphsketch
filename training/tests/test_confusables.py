import numpy as np
import pytest

from conftest import real_stage_dir_or_skip
from glyphsketch.confusables import (
    GROUPS_FILE,
    ConfusableGroups,
    complete_linkage_groups,
    dilate,
    shape_signature,
    tolerant_similarity,
)


def _mask(rows: list[str]) -> np.ndarray:
    return np.array([[char == "#" for char in row] for row in rows])


def test_dilation_grows_by_one_pixel() -> None:
    mask = _mask(["...", ".#.", "..."])
    assert dilate(mask).all()


def test_similarity_is_one_for_identical_and_zero_for_disjoint_shapes() -> None:
    shape = _mask(["#....", "#....", "#....", "#....", "#...."])
    far = _mask(["....#", "....#", "....#", "....#", "....#"])
    assert tolerant_similarity(shape, shape) == 1.0
    assert tolerant_similarity(shape, far) == 0.0


def test_similarity_tolerates_a_one_pixel_shift() -> None:
    shape = _mask(["#....", "#....", "#...."])
    shifted = _mask([".#...", ".#...", ".#..."])
    assert tolerant_similarity(shape, shifted) == 1.0


def test_similarity_is_symmetric_in_coverage() -> None:
    small = _mask(["#....", ".....", "....."])
    large = _mask(["#####", "#####", "#####"])
    assert tolerant_similarity(small, large) < 0.5


def test_signature_downsamples_renders() -> None:
    render = np.zeros((128, 128), dtype=np.uint8)
    render[:, 60:68] = 255
    signature = shape_signature(render)
    assert signature.shape == (32, 32)
    assert signature[:, 15:17].all() and not signature[:, :14].any()


def test_complete_linkage_does_not_chain_dissimilar_characters() -> None:
    similar = {(1, 2): 0.95, (2, 3): 0.9, (1, 3): 0.5, (4, 5): 0.99}

    def similarity(first: int, second: int) -> float:
        return similar.get((min(first, second), max(first, second)), 0.0)

    groups = complete_linkage_groups([(1, 2), (2, 3), (4, 5)], similarity, threshold=0.85)
    assert [1, 2] in groups
    assert [3] in groups
    assert [4, 5] in groups


def test_group_lookup_maps_members_to_the_smallest_code_point() -> None:
    groups = ConfusableGroups([[0x41, 0x391, 0x410]])
    group_of = groups.group_of()
    assert group_of[0x410] == 0x41
    assert groups.representative(0x42, group_of) == 0x42


@pytest.mark.data
def test_real_groups_merge_true_homoglyphs_only() -> None:
    groups = ConfusableGroups.load(real_stage_dir_or_skip("confusables", GROUPS_FILE) / GROUPS_FILE)
    group_of = groups.group_of()

    def same(first: str, second: str) -> bool:
        return group_of.get(ord(first), ord(first)) == group_of.get(ord(second), ord(second))

    assert same("A", "Α") and same("A", "А")
    assert same("o", "О") and same("x", "х")
    assert same("·", "⋅")
    assert not same("A", "𝔄")
    assert not same("A", "𝒜")
    assert not same("6", "O")
    assert not same("1", "l")
    # The largest group is the circles (o, O, and round letters of some 40 scripts since D40).
    assert max(len(group) for group in groups.groups) < 80


def test_compatibility_forms_join_their_base_when_they_look_alike() -> None:
    from glyphsketch.confusables import attach_compatibility_forms

    def similarity(a: int, b: int) -> float:
        return 0.5 if 0xFE82 in (a, b) else 0.95

    groups = [[0x4F, 0x6F, 0x41E]]
    bases = {0xFF2F: 0x4F, 0xFF21: 0x41, 0xFE82: 0x622}  # Ｏ → O, Ａ → A, ﺂ (final) → آ
    attached = attach_compatibility_forms(groups, bases, similarity, 0.85)
    assert [0x4F, 0x6F, 0x41E, 0xFF2F] in attached
    assert [0x41, 0xFF21] in attached  # the base had no group yet
    assert not any(0xFE82 in group for group in attached)  # a final form that looks different


def test_joiners_join_existing_groups_instead_of_splitting_them() -> None:
    from glyphsketch.confusables import attach_to_groups

    # o/O form a group; a new-script circle (0x1000) looks like both, a new-script stroke
    # (0x1001) like nothing, and a second circle (0x1002) only like the first circle.
    looks = {frozenset((0x4F, 0x6F)), frozenset((0x1000, 0x6F)), frozenset((0x1000, 0x4F))}

    def similarity(a: int, b: int) -> float:
        return 0.95 if frozenset((a, b)) in looks else 0.2

    candidates = [(0x4F, 0x6F), (0x6F, 0x1000), (0x1001, 0x6F), (0x1000, 0x1002)]
    groups, placed = attach_to_groups([[0x4F, 0x6F]], {0x1000, 0x1001, 0x1002}, candidates,
                                      similarity, 0.85)  # fmt: skip
    assert groups == [[0x4F, 0x6F, 0x1000]]
    assert placed == {0x1000}
