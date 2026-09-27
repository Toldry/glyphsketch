"""Binary files of the exported model and glyph index (spec: docs/export_format.md).

Everything is little-endian. Every float32 array starts at a multiple of 4 bytes from
the start of the file, so readers can view it in place.
"""

import struct
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path

import numpy as np

from glyphsketch.export.ops import (
    Conv,
    GlobalAveragePool,
    L2Normalize,
    Linear,
    Operation,
    ResidualAdd,
    ResidualBegin,
    dequantize,
    quantize_per_channel,
)
from glyphsketch.model.index import GlyphIndex

MODEL_MAGIC = b"GSKM"
INDEX_MAGIC = b"GSKI"
FORMAT_VERSION = 1

CONV, RESIDUAL_BEGIN, RESIDUAL_ADD, GLOBAL_AVERAGE_POOL, LINEAR, L2_NORMALIZE = range(1, 7)
SIMPLE_OPERATIONS: dict[int, Operation] = {
    RESIDUAL_BEGIN: ResidualBegin(),
    RESIDUAL_ADD: ResidualAdd(),
    GLOBAL_AVERAGE_POOL: GlobalAveragePool(),
    L2_NORMALIZE: L2Normalize(),
}


def _pad(buffer: BytesIO) -> None:
    buffer.write(b"\0" * (-buffer.tell() % 4))


def _write_quantized(buffer: BytesIO, weight: np.ndarray, bias: np.ndarray) -> None:
    values, scales = quantize_per_channel(weight)
    buffer.write(values.astype(np.int8).tobytes())
    _pad(buffer)
    buffer.write(scales.astype("<f4").tobytes())
    buffer.write(bias.astype("<f4").tobytes())


def model_bytes(operations: Sequence[Operation], input_size: int) -> bytes:
    linear = [operation for operation in operations if isinstance(operation, Linear)]
    buffer = BytesIO()
    buffer.write(MODEL_MAGIC)
    buffer.write(struct.pack("<HHHH", FORMAT_VERSION, input_size, len(linear[-1].bias),
                             len(operations)))  # fmt: skip
    for operation in operations:
        if isinstance(operation, Conv):
            out_channels, per_group, kernel, _ = operation.weight.shape
            buffer.write(struct.pack("<BHHBBHB", CONV, per_group * operation.groups,
                                     out_channels, kernel, operation.stride, operation.groups,
                                     int(operation.relu6)))  # fmt: skip
            _pad(buffer)
            _write_quantized(buffer, operation.weight, operation.bias)
        elif isinstance(operation, Linear):
            out_features, in_features = operation.weight.shape
            buffer.write(struct.pack("<BHH", LINEAR, in_features, out_features))
            _pad(buffer)
            _write_quantized(buffer, operation.weight, operation.bias)
        else:
            kind = next(key for key, value in SIMPLE_OPERATIONS.items() if value == operation)
            buffer.write(struct.pack("<B", kind))
    return buffer.getvalue()


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    def unpack(self, layout: str) -> tuple[int, ...]:
        values = struct.unpack_from(layout, self.data, self.offset)
        self.offset += struct.calcsize(layout)
        return values

    def align(self) -> None:
        self.offset += -self.offset % 4

    def array(self, dtype: str, count: int) -> np.ndarray:
        array = np.frombuffer(self.data, dtype=dtype, count=count, offset=self.offset)
        self.offset += array.nbytes
        return array


def _read_quantized(reader: _Reader, shape: tuple[int, ...]) -> tuple[np.ndarray, np.ndarray]:
    values = reader.array("i1", int(np.prod(shape))).reshape(shape)
    reader.align()
    scales = reader.array("<f4", shape[0])
    bias = reader.array("<f4", shape[0]).astype(np.float32)
    return dequantize(values, scales), bias


def read_model(data: bytes) -> tuple[list[Operation], int]:
    """(operations with dequantized weights, input size)."""
    if data[:4] != MODEL_MAGIC:
        raise ValueError("Not a glyphsketch model file")
    reader = _Reader(data)
    reader.offset = 4
    version, input_size, _, count = reader.unpack("<HHHH")
    if version != FORMAT_VERSION:
        raise ValueError(f"Unsupported model format version {version}")
    operations: list[Operation] = []
    for _ in range(count):
        (kind,) = reader.unpack("<B")
        if kind == CONV:
            in_channels, out_channels, kernel, stride, groups, relu6 = reader.unpack("<HHBBHB")
            reader.align()
            weight, bias = _read_quantized(
                reader, (out_channels, in_channels // groups, kernel, kernel)
            )
            operations.append(Conv(weight, bias, stride, groups, bool(relu6)))
        elif kind == LINEAR:
            in_features, out_features = reader.unpack("<HH")
            reader.align()
            weight, bias = _read_quantized(reader, (out_features, in_features))
            operations.append(Linear(weight, bias))
        else:
            operations.append(SIMPLE_OPERATIONS[kind])
    if reader.offset != len(data):
        raise ValueError("Trailing bytes after the last operation")
    return operations, input_size


def quantize_vectors(vectors: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Symmetric int8 per vector: (int8 values, float32 scales)."""
    return quantize_per_channel(vectors)


def index_bytes(index: GlyphIndex) -> bytes:
    values, scales = quantize_vectors(index.vectors)
    buffer = BytesIO()
    buffer.write(INDEX_MAGIC)
    buffer.write(struct.pack("<HHII", FORMAT_VERSION, index.vectors.shape[1],
                             len(index.code_points), len(index.vectors)))  # fmt: skip
    buffer.write(index.code_points.astype("<u4").tobytes())
    buffer.write(index.starts.astype("<u4").tobytes())
    buffer.write(scales.astype("<f4").tobytes())
    buffer.write(values.astype(np.int8).tobytes())
    return buffer.getvalue()


def read_index(data: bytes) -> GlyphIndex:
    if data[:4] != INDEX_MAGIC:
        raise ValueError("Not a glyphsketch index file")
    reader = _Reader(data)
    reader.offset = 4
    version, dims, characters, vectors = reader.unpack("<HHII")
    if version != FORMAT_VERSION:
        raise ValueError(f"Unsupported index format version {version}")
    code_points = reader.array("<u4", characters).astype(np.int64)
    starts = reader.array("<u4", characters).astype(np.int64)
    scales = reader.array("<f4", vectors)
    values = reader.array("i1", vectors * dims).reshape(vectors, dims)
    if reader.offset != len(data):
        raise ValueError("Trailing bytes after the index vectors")
    return GlyphIndex(dequantize(values, scales), code_points, starts)


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
