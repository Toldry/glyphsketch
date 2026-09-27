"""The encoder as a flat list of operations, the form the inference engines execute.

``fold_encoder`` turns a trained ``GlyphEncoder`` into seven kinds of operation. Batch
norm is folded into the preceding convolution, and an optional projection (PCA, chosen
at export) is folded into the final linear layer:

* ``Conv``: 2-D convolution, "same" padding (``kernel // 2``), optional ReLU6. Grouped only
  as depthwise (``groups == in == out``);
* ``ResidualBegin`` / ``ResidualAdd``: remember the current tensor, and later add it back;
* ``GlobalAveragePool``, ``Linear`` and ``L2Normalize``.

Tensors are (channels, height, width) per image. ``run_numpy`` is the reference that the
TypeScript and Kotlin engines follow; ``run_torch`` executes the same list quickly for
large evaluations.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import torch
from torch import nn
from torch.nn import functional

from glyphsketch.model.encoder import ConvBn, GlyphEncoder, InvertedResidual


@dataclass(frozen=True)
class Conv:
    weight: np.ndarray  # (out, in / groups, k, k), float32
    bias: np.ndarray  # (out,)
    stride: int
    groups: int
    relu6: bool


@dataclass(frozen=True)
class ResidualBegin:
    pass


@dataclass(frozen=True)
class ResidualAdd:
    pass


@dataclass(frozen=True)
class GlobalAveragePool:
    pass


@dataclass(frozen=True)
class Linear:
    weight: np.ndarray  # (out, in), float32
    bias: np.ndarray


@dataclass(frozen=True)
class L2Normalize:
    pass


Operation = Conv | ResidualBegin | ResidualAdd | GlobalAveragePool | Linear | L2Normalize


def fold_conv_bn(block: ConvBn) -> Conv:
    conv, batch_norm = block[0], block[1]
    assert isinstance(conv, nn.Conv2d) and isinstance(batch_norm, nn.BatchNorm2d)
    assert batch_norm.running_var is not None and batch_norm.running_mean is not None
    factor = batch_norm.weight.detach() / torch.sqrt(batch_norm.running_var + batch_norm.eps)
    weight = conv.weight.detach() * factor[:, None, None, None]
    bias = batch_norm.bias.detach() - batch_norm.running_mean * factor
    stride = conv.stride[0] if isinstance(conv.stride, tuple) else int(conv.stride)
    return Conv(
        weight=weight.float().numpy().copy(),
        bias=bias.float().numpy().copy(),
        stride=stride,
        groups=conv.groups,
        relu6=len(block) > 2,
    )


def fold_encoder(model: GlyphEncoder, projection: np.ndarray | None = None) -> list[Operation]:
    """Operations equal to ``model`` in eval mode; ``projection`` is (embedding, d)."""
    operations: list[Operation] = []
    for layer in model.features:
        if isinstance(layer, InvertedResidual):
            if layer.use_residual:
                operations.append(ResidualBegin())
            operations += [fold_conv_bn(block) for block in layer.layers]  # type: ignore[arg-type]
            if layer.use_residual:
                operations.append(ResidualAdd())
        else:
            assert isinstance(layer, ConvBn)
            operations.append(fold_conv_bn(layer))
    operations.append(GlobalAveragePool())
    weight = model.projection.weight.detach().float().numpy()
    bias = model.projection.bias.detach().float().numpy()
    if projection is not None:
        weight = projection.T @ weight
        bias = projection.T @ bias
    operations += [Linear(weight.astype(np.float32), bias.astype(np.float32)), L2Normalize()]
    return operations


def quantize_per_channel(weight: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Symmetric int8 per output channel (axis 0): (int8 values, float32 scales)."""
    flat = weight.reshape(len(weight), -1)
    scales = np.abs(flat).max(axis=1) / 127.0
    scales = np.where(scales > 0, scales, 1.0).astype(np.float32)
    values = np.clip(np.round(flat / scales[:, None]), -127, 127).astype(np.int8)
    return values.reshape(weight.shape), scales


def dequantize(values: np.ndarray, scales: np.ndarray) -> np.ndarray:
    shape = (-1,) + (1,) * (values.ndim - 1)
    return (values.astype(np.float32) * scales.reshape(shape)).astype(np.float32)


def quantized(operations: Sequence[Operation]) -> list[Operation]:
    """The operations with every weight rounded through int8, as the exported file holds them."""
    result: list[Operation] = []
    for operation in operations:
        if isinstance(operation, Conv):
            weight = dequantize(*quantize_per_channel(operation.weight))
            result.append(Conv(weight, operation.bias, operation.stride, operation.groups,
                               operation.relu6))  # fmt: skip
        elif isinstance(operation, Linear):
            result.append(Linear(dequantize(*quantize_per_channel(operation.weight)),
                                 operation.bias))  # fmt: skip
        else:
            result.append(operation)
    return result


def conv_numpy(inputs: np.ndarray, operation: Conv) -> np.ndarray:
    """Reference convolution of one (C, H, W) tensor, written for clarity."""
    weight, stride = operation.weight, operation.stride
    out_channels, _, kernel, _ = weight.shape
    pad = kernel // 2
    channels, height, width = inputs.shape
    padded = np.zeros((channels, height + 2 * pad, width + 2 * pad), dtype=np.float32)
    padded[:, pad : pad + height, pad : pad + width] = inputs
    out_height = (height + 2 * pad - kernel) // stride + 1
    out_width = (width + 2 * pad - kernel) // stride + 1
    output = np.zeros((out_channels, out_height, out_width), dtype=np.float32)
    for ky in range(kernel):
        for kx in range(kernel):
            window = padded[
                :,
                ky : ky + stride * (out_height - 1) + 1 : stride,
                kx : kx + stride * (out_width - 1) + 1 : stride,
            ]
            if operation.groups == 1:
                output += np.einsum("oi,ihw->ohw", weight[:, :, ky, kx], window)
            else:  # depthwise
                output += weight[:, 0, ky, kx][:, None, None] * window
    output += operation.bias[:, None, None]
    return np.clip(output, 0.0, 6.0) if operation.relu6 else output


def run_numpy(operations: Sequence[Operation], image: np.ndarray) -> np.ndarray:
    """Embedding of one image: (S, S) float32, ink = 1.0."""
    tensor = image[None, :, :].astype(np.float32)
    saved: list[np.ndarray] = []
    for operation in operations:
        if isinstance(operation, Conv):
            tensor = conv_numpy(tensor, operation)
        elif isinstance(operation, ResidualBegin):
            saved.append(tensor)
        elif isinstance(operation, ResidualAdd):
            tensor = tensor + saved.pop()
        elif isinstance(operation, GlobalAveragePool):
            tensor = tensor.mean(axis=(1, 2))
        elif isinstance(operation, Linear):
            tensor = operation.weight @ tensor + operation.bias
        else:
            tensor = tensor / max(float(np.linalg.norm(tensor)), 1e-12)
    return tensor.astype(np.float32)


class OperationsModule(nn.Module):
    """``run_torch``: the operation list as a torch module, for batched evaluation."""

    def __init__(self, operations: Sequence[Operation]) -> None:
        super().__init__()
        self.operations = list(operations)
        self.tensors = nn.ParameterList()
        for operation in self.operations:
            if isinstance(operation, Conv | Linear):
                self.tensors.append(nn.Parameter(torch.from_numpy(operation.weight),
                                                 requires_grad=False))  # fmt: skip
                self.tensors.append(nn.Parameter(torch.from_numpy(operation.bias),
                                                 requires_grad=False))  # fmt: skip

    def forward(self, images: torch.Tensor) -> torch.Tensor:
        tensor = images
        saved: list[torch.Tensor] = []
        parameters = iter(self.tensors)
        for operation in self.operations:
            if isinstance(operation, Conv):
                weight, bias = next(parameters), next(parameters)
                padding = operation.weight.shape[-1] // 2
                tensor = functional.conv2d(
                    tensor, weight, bias, operation.stride, padding, groups=operation.groups
                )
                if operation.relu6:
                    tensor = functional.relu6(tensor)
            elif isinstance(operation, ResidualBegin):
                saved.append(tensor)
            elif isinstance(operation, ResidualAdd):
                tensor = tensor + saved.pop()
            elif isinstance(operation, GlobalAveragePool):
                tensor = tensor.mean(dim=(2, 3))
            elif isinstance(operation, Linear):
                weight, bias = next(parameters), next(parameters)
                tensor = functional.linear(tensor, weight, bias)
            else:
                tensor = functional.normalize(tensor, dim=1)
        return tensor


def multiply_adds(operations: Sequence[Operation], input_size: int) -> int:
    total, size = 0, input_size
    for operation in operations:
        if isinstance(operation, Conv):
            size = (size + operation.stride - 1) // operation.stride
            total += operation.weight.size * size * size
        elif isinstance(operation, Linear):
            total += operation.weight.size
    return total
