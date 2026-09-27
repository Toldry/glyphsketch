import numpy as np
import pytest
import torch

from glyphsketch.model.data import (
    BatchSampler,
    TrainingData,
    assemble_batch,
    group_by_character,
    group_ids,
    nearest_other_group,
    same_group_mask,
)
from glyphsketch.model.encoder import GlyphEncoder, count_multiply_adds, count_parameters
from glyphsketch.model.index import GlyphIndex
from glyphsketch.model.loss import ContrastiveLoss, masked_info_nce
from glyphsketch.model.train import TrainingConfig, learning_rate_at


def test_encoder_outputs_unit_vectors() -> None:
    model = GlyphEncoder()
    model.eval()
    with torch.no_grad():
        embeddings = model(torch.rand(3, 1, 64, 64))
    assert embeddings.shape == (3, 128)
    assert torch.allclose(embeddings.norm(dim=1), torch.ones(3), atol=1e-5)


def test_encoder_fits_the_mobile_budget() -> None:
    model = GlyphEncoder()
    assert count_multiply_adds(model) < 40_000_000
    assert count_parameters(model) < 1_000_000


def test_masked_logits_do_not_count_as_negatives() -> None:
    queries = torch.nn.functional.normalize(torch.tensor([[1.0, 0.0], [1.0, 0.1]]), dim=1)
    keys = queries.clone()
    scale = torch.tensor(20.0)
    no_mask = torch.zeros(2, 2, dtype=torch.bool)
    mask = torch.tensor([[False, True], [True, False]])
    unmasked = masked_info_nce(queries, keys, scale, no_mask)
    masked = masked_info_nce(queries, keys, scale, mask)
    assert masked < unmasked
    assert masked == pytest.approx(0.0, abs=1e-4)


def test_contrastive_loss_is_lower_for_matching_embeddings() -> None:
    torch.manual_seed(0)
    loss = ContrastiveLoss()
    anchors = torch.nn.functional.normalize(torch.randn(8, 16), dim=1)
    mask = torch.zeros(8, 8, dtype=torch.bool)
    matched = loss(anchors, anchors, anchors, mask)["loss"]
    random = torch.nn.functional.normalize(torch.randn(8, 16), dim=1)
    mismatched = loss(anchors, random, random, mask)["loss"]
    assert matched < mismatched


def test_group_by_character_sorts_and_drops_unknown_code_points() -> None:
    images = np.arange(5, dtype=np.uint8)[:, None, None].repeat(4, 1).repeat(4, 2)
    pool = group_by_character(images, np.array([66, 65, 99, 66, 65]), np.array([65, 66]))
    assert pool.offsets.tolist() == [0, 2, 4]
    assert pool.images[:, 0, 0].tolist() == [1, 4, 0, 3]
    assert pool.count(1) == 2


def test_same_group_mask_and_group_ids() -> None:
    groups = group_ids(np.array([0x41, 0x391, 0x42]), {0x41: 0x41, 0x391: 0x41})
    assert groups[0] == groups[1] != groups[2]
    mask = same_group_mask(groups)
    assert mask.tolist() == [[False, True, False], [True, False, False], [False, False, False]]


def test_nearest_other_group_skips_group_members() -> None:
    features = np.array([[1.0, 0.0], [1.0, 0.0], [0.8, 0.6], [0.0, 1.0]])
    groups = np.array([0, 0, 1, 2])
    neighbours = nearest_other_group(features, groups, neighbours=1)
    assert neighbours[:, 0].tolist() == [2, 2, 0, 2]


def _toy_data(characters: int = 20) -> TrainingData:
    images = np.random.default_rng(0).integers(0, 255, (characters * 3, 64, 64), dtype=np.uint8)
    code_points = np.repeat(np.arange(characters), 3)
    pool = group_by_character(images, code_points, np.arange(characters))
    return TrainingData(
        characters=np.arange(characters),
        groups=np.arange(characters),
        synthetic=pool,
        glyphs=pool,
    )


def test_batches_hold_distinct_characters_with_hard_neighbourhoods() -> None:
    rng = np.random.default_rng(1)
    neighbours = np.array([[(index + offset) % 20 for offset in (1, 2, 3)] for index in range(20)])
    sampler = BatchSampler(20, 10, neighbours, 0.5, 4, rng)
    for _ in range(20):
        characters = sampler.sample()
        assert len(characters) == 10 and len(set(characters.tolist())) == 10
    batch = assemble_batch(_toy_data(), sampler.sample(), 0.0, rng)
    assert batch.first_view.shape == (10, 1, 64, 64)
    assert float(batch.glyphs.max()) <= 1.0
    assert not batch.same_group.any()


def test_learning_rate_warms_up_and_decays() -> None:
    config = TrainingConfig(steps=100, warmup_steps=10, learning_rate=1.0)
    assert learning_rate_at(0, config) == pytest.approx(0.1)
    assert learning_rate_at(10, config) == pytest.approx(1.0)
    assert learning_rate_at(99, config) < 0.01


def test_a_time_budget_decays_the_learning_rate_before_the_last_step() -> None:
    config = TrainingConfig(steps=100, warmup_steps=10, learning_rate=1.0, time_budget_seconds=60)
    assert learning_rate_at(20, config, elapsed_seconds=0) > 0.9
    assert learning_rate_at(20, config, elapsed_seconds=59) < 0.01


def test_index_scores_take_the_best_vector_per_character() -> None:
    vectors = np.array([[1.0, 0.0], [0.0, 1.0], [0.6, 0.8]], dtype=np.float32)
    index = GlyphIndex.from_rows(vectors, np.array([7, 5, 7]))
    assert index.code_points.tolist() == [5, 7]
    code_points, scores = index.top_k(np.array([[0.0, 1.0]], dtype=np.float32), 2)
    assert code_points.tolist() == [[5, 7]]
    assert scores[0].tolist() == pytest.approx([1.0, 0.8])
    averaged = index.averaged()
    assert len(averaged.vectors) == 2
    assert np.allclose(np.linalg.norm(averaged.vectors, axis=1), 1.0)
