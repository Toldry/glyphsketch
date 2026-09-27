import numpy as np
import pytest
import torch

from glyphsketch.export.formats import index_bytes, model_bytes, read_index, read_model
from glyphsketch.export.ops import (
    Conv,
    OperationsModule,
    fold_encoder,
    multiply_adds,
    quantize_per_channel,
    quantized,
    run_numpy,
)
from glyphsketch.model.encoder import GlyphEncoder, count_multiply_adds
from glyphsketch.model.index import GlyphIndex


@pytest.fixture(scope="module")
def trained_like_model() -> GlyphEncoder:
    """An encoder with non-trivial batch-norm statistics, as after training."""
    torch.manual_seed(0)
    model = GlyphEncoder()
    model.train()
    with torch.no_grad():
        for _ in range(3):
            model(torch.rand(16, 1, 64, 64))
        for module in model.modules():
            if isinstance(module, torch.nn.BatchNorm2d):
                module.weight.uniform_(0.5, 1.5)
                module.bias.uniform_(-0.2, 0.2)
    return model.eval()


def _images(count: int) -> torch.Tensor:
    generator = torch.Generator().manual_seed(1)
    return (torch.rand(count, 1, 64, 64, generator=generator) > 0.8).float()


def test_folded_operations_match_the_model(trained_like_model: GlyphEncoder) -> None:
    operations = fold_encoder(trained_like_model)
    images = _images(4)
    with torch.no_grad():
        expected = trained_like_model(images).numpy()
        folded = OperationsModule(operations)(images).numpy()
    assert np.abs(folded - expected).max() < 1e-5
    assert multiply_adds(operations, 64) == count_multiply_adds(trained_like_model)


def test_numpy_reference_matches_torch(trained_like_model: GlyphEncoder) -> None:
    operations = fold_encoder(trained_like_model)
    images = _images(2)
    with torch.no_grad():
        expected = OperationsModule(operations)(images).numpy()
    for image, embedding in zip(images[:, 0].numpy(), expected, strict=True):
        assert np.abs(run_numpy(operations, image) - embedding).max() < 1e-5


def test_projection_folds_into_the_last_layer(trained_like_model: GlyphEncoder) -> None:
    projection = np.linalg.qr(np.random.default_rng(0).normal(size=(128, 32)))[0]
    images = _images(3)
    with torch.no_grad():
        full = trained_like_model(images).numpy()
        projected = OperationsModule(fold_encoder(trained_like_model, projection))(images).numpy()
    expected = full @ projection
    expected /= np.linalg.norm(expected, axis=1, keepdims=True)
    assert projected.shape == (3, 32)
    assert np.abs(projected - expected).max() < 1e-5


def test_int8_weights_stay_close(trained_like_model: GlyphEncoder) -> None:
    operations = fold_encoder(trained_like_model)
    images = _images(8)
    with torch.no_grad():
        exact = OperationsModule(operations)(images).numpy()
        rounded = OperationsModule(quantized(operations))(images).numpy()
    assert (exact * rounded).sum(axis=1).min() > 0.995


def test_per_channel_quantization_bounds_the_error() -> None:
    weight = np.random.default_rng(2).normal(size=(4, 3, 3, 3)).astype(np.float32)
    weight[1] *= 100
    values, scales = quantize_per_channel(weight)
    assert values.dtype == np.int8 and np.abs(values).max() == 127
    error = np.abs(values * scales[:, None, None, None] - weight)
    assert np.all(error <= scales[:, None, None, None] / 2 + 1e-6)


def test_model_file_round_trip(trained_like_model: GlyphEncoder) -> None:
    operations = fold_encoder(trained_like_model)
    data = model_bytes(operations, 64)
    loaded, input_size = read_model(data)
    assert input_size == 64
    expected = quantized(operations)
    assert [type(op) for op in loaded] == [type(op) for op in expected]
    for got, want in zip(loaded, expected, strict=True):
        if isinstance(got, Conv):
            assert isinstance(want, Conv)
            assert np.allclose(got.weight, want.weight) and np.allclose(got.bias, want.bias)
            assert (got.stride, got.groups, got.relu6) == (want.stride, want.groups, want.relu6)
    parameters = sum(p.numel() for p in trained_like_model.parameters())
    assert len(data) < 1.3 * parameters  # about one byte per weight


def test_index_file_round_trip() -> None:
    vectors = np.random.default_rng(3).normal(size=(7, 16)).astype(np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    index = GlyphIndex.from_rows(vectors, np.array([66, 65, 66, 67, 65, 65, 900]))
    loaded = read_index(index_bytes(index))
    assert loaded.code_points.tolist() == index.code_points.tolist()
    assert loaded.starts.tolist() == index.starts.tolist()
    assert np.abs(loaded.vectors - index.vectors).max() < 0.01


def test_reading_rejects_other_files() -> None:
    with pytest.raises(ValueError):
        read_model(b"GSKI" + bytes(20))
    with pytest.raises(ValueError):
        read_index(b"nope")


def test_pca_basis_is_orthonormal_and_ordered_by_variance() -> None:
    from glyphsketch.export.build import pca_basis, project

    rng = np.random.default_rng(4)
    vectors = (rng.normal(size=(200, 8)) * np.array([5, 4, 3, 2, 1, 0.5, 0.2, 0.1])).astype(
        np.float32
    )
    basis = pca_basis(vectors)
    assert np.allclose(basis.T @ basis, np.eye(8), atol=1e-4)
    spread = (vectors @ basis).std(axis=0)
    assert np.all(np.diff(spread) <= 1e-4)
    projected = project(vectors, basis[:, :3])
    assert projected.shape == (200, 3)
    assert np.allclose(np.linalg.norm(projected, axis=1), 1.0, atol=1e-5)


def test_the_ranker_rebuilt_from_metadata_uses_the_stored_values() -> None:
    from glyphsketch.export.build import ranker_from_metadata

    metadata = {
        "ranking": {"prior_weight": 0.01},
        "columns": [
            "code_point", "name", "block", "script", "general_category", "group", "log_prior",
        ],
        "characters": [
            [65, "LATIN CAPITAL LETTER A", "Basic Latin", "Latin", "Lu", 65, -5.0],
            [913, "GREEK CAPITAL LETTER ALPHA", "Greek and Coptic", "Greek", "Lu", 65, -8.0],
            [66, "LATIN CAPITAL LETTER B", "Basic Latin", "Latin", "Lu", 66, -6.0],
        ],
    }  # fmt: skip
    index = GlyphIndex.from_rows(np.eye(3, dtype=np.float32), np.array([65, 913, 66]))
    ranker = ranker_from_metadata(metadata, index)
    tiles = ranker.tiles(np.array([0.5, 0.5, 0.52], dtype=np.float32), 2, ("Greek",))
    assert [tile.representative for tile in tiles] == [913, 66]
    assert tiles[0].members == (913, 65)
