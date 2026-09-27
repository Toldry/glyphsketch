"""A small CNN that maps a 64×64 drawing or glyph image to a unit-length embedding.

The design follows MobileNetV2 (inverted residual blocks: 1×1 expansion, 3×3 depthwise,
1×1 projection) because it gives the most accuracy per multiply-add, and the engines in
TypeScript and Kotlin have to run it in well under 50 ms. It uses only operations those
engines implement: 3×3 convolution (standard and depthwise), 1×1 convolution, batch norm
(folded into the convolutions at export), ReLU6, global average pooling and one linear
layer. The default configuration costs about 22M multiply-adds per image and has about
0.5M parameters.
"""

from dataclasses import dataclass, field

import torch
from torch import nn
from torch.nn import functional

INPUT_SIZE = 64


@dataclass(frozen=True)
class BlockSpec:
    output_channels: int
    expansion: int
    stride: int


@dataclass(frozen=True)
class EncoderConfig:
    stem_channels: int = 16
    blocks: tuple[BlockSpec, ...] = field(
        default_factory=lambda: (
            BlockSpec(24, 2, 1),
            BlockSpec(48, 3, 2),
            BlockSpec(48, 3, 1),
            BlockSpec(96, 3, 2),
            BlockSpec(96, 3, 1),
            BlockSpec(192, 3, 2),
            BlockSpec(192, 3, 1),
        )
    )
    head_channels: int = 384
    embedding_dim: int = 128


class ConvBn(nn.Sequential):
    def __init__(
        self,
        input_channels: int,
        output_channels: int,
        kernel_size: int,
        stride: int = 1,
        groups: int = 1,
        activation: bool = True,
    ) -> None:
        layers: list[nn.Module] = [
            nn.Conv2d(
                input_channels,
                output_channels,
                kernel_size,
                stride=stride,
                padding=kernel_size // 2,
                groups=groups,
                bias=False,
            ),
            nn.BatchNorm2d(output_channels),
        ]
        if activation:
            layers.append(nn.ReLU6(inplace=True))
        super().__init__(*layers)


class InvertedResidual(nn.Module):
    def __init__(self, input_channels: int, spec: BlockSpec) -> None:
        super().__init__()
        hidden = input_channels * spec.expansion
        self.use_residual = spec.stride == 1 and input_channels == spec.output_channels
        self.layers = nn.Sequential(
            ConvBn(input_channels, hidden, 1),
            ConvBn(hidden, hidden, 3, stride=spec.stride, groups=hidden),
            ConvBn(hidden, spec.output_channels, 1, activation=False),
        )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        outputs: torch.Tensor = self.layers(inputs)
        return inputs + outputs if self.use_residual else outputs


class GlyphEncoder(nn.Module):
    """Maps (N, 1, 64, 64) images with ink = 1.0 and paper = 0.0 to (N, D) unit vectors."""

    def __init__(self, config: EncoderConfig | None = None) -> None:
        super().__init__()
        self.config = config or EncoderConfig()
        layers: list[nn.Module] = [ConvBn(1, self.config.stem_channels, 3, stride=2)]
        channels = self.config.stem_channels
        for spec in self.config.blocks:
            layers.append(InvertedResidual(channels, spec))
            channels = spec.output_channels
        layers.append(ConvBn(channels, self.config.head_channels, 1))
        self.features = nn.Sequential(*layers)
        self.projection = nn.Linear(self.config.head_channels, self.config.embedding_dim)

    def forward(self, images: torch.Tensor) -> torch.Tensor:
        features = self.features(images)
        pooled = features.mean(dim=(2, 3))
        return functional.normalize(self.projection(pooled), dim=1)


def count_parameters(model: nn.Module) -> int:
    return sum(parameter.numel() for parameter in model.parameters())


def count_multiply_adds(model: GlyphEncoder, input_size: int = INPUT_SIZE) -> int:
    """Multiply-adds of one forward pass (convolutions and the linear layer)."""
    total = 0

    def hook(module: nn.Module, inputs: tuple[torch.Tensor, ...], output: torch.Tensor) -> None:
        nonlocal total
        if isinstance(module, nn.Conv2d):
            kernel_mults = module.kernel_size[0] * module.kernel_size[1]
            per_output = kernel_mults * module.in_channels // module.groups
            total += output.numel() * per_output
        elif isinstance(module, nn.Linear):
            total += module.in_features * module.out_features

    handles = [
        module.register_forward_hook(hook)
        for module in model.modules()
        if isinstance(module, nn.Conv2d | nn.Linear)
    ]
    was_training = model.training
    model.eval()
    with torch.no_grad():
        model(torch.zeros(1, 1, input_size, input_size))
    model.train(was_training)
    for handle in handles:
        handle.remove()
    return total
