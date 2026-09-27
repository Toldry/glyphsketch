"""Training loop for the glyph encoder (CPU in the devcontainer, GPU on Kaggle).

AdamW with linear warm-up and cosine decay, a wall-clock budget (the decay follows whichever
of steps and time runs out first, so a run cut short by time still ends annealed), periodic
refresh of the hard-negative neighbours from the model's own glyph embeddings, and a JSON log.
"""

import json
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import torch

from glyphsketch.model.data import (
    BatchSampler,
    TrainingData,
    assemble_batch,
    glyph_hog_neighbours,
    nearest_other_group,
    to_tensor,
)
from glyphsketch.model.encoder import EncoderConfig, GlyphEncoder
from glyphsketch.model.loss import ContrastiveLoss

CHECKPOINT_FILE = "encoder.pt"
LOG_FILE = "training_log.json"


@dataclass(frozen=True)
class TrainingConfig:
    steps: int = 6000
    batch_characters: int = 256
    learning_rate: float = 3e-3
    weight_decay: float = 1e-4
    warmup_steps: int = 300
    hard_fraction: float = 0.5
    neighbourhood_size: int = 8
    neighbours: int = 24
    refresh_every: int = 500
    real_probability: float = 0.0
    time_budget_seconds: float | None = None
    seed: int = 0
    log_every: int = 50
    encoder: EncoderConfig = field(default_factory=EncoderConfig)


def learning_rate_at(step: int, config: TrainingConfig, elapsed_seconds: float = 0.0) -> float:
    if step < config.warmup_steps:
        return config.learning_rate * (step + 1) / config.warmup_steps
    progress = (step - config.warmup_steps) / max(1, config.steps - config.warmup_steps)
    if config.time_budget_seconds:
        progress = max(progress, elapsed_seconds / config.time_budget_seconds)
    return config.learning_rate * 0.5 * (1 + math.cos(math.pi * min(progress, 1.0)))


def model_input(images: torch.Tensor, device: torch.device) -> torch.Tensor:
    """Channels-last layout: about 1.4× faster convolutions on CPU (and fine on GPU)."""
    return images.to(device).contiguous(memory_format=torch.channels_last)


@torch.no_grad()
def embed_uint8_images(
    model: GlyphEncoder, images: np.ndarray, device: torch.device, batch: int = 1024
) -> np.ndarray:
    was_training = model.training
    model.eval()
    parts = []
    for start in range(0, len(images), batch):
        inputs = model_input(to_tensor(images[start : start + batch]), device)
        parts.append(model(inputs).cpu().numpy())
    model.train(was_training)
    return np.concatenate(parts).astype(np.float32)


def model_neighbours(
    model: GlyphEncoder, data: TrainingData, neighbours: int, device: torch.device
) -> np.ndarray:
    """Hard-negative candidates from the model: one glyph render per character."""
    first_glyphs = data.glyphs.images[data.glyphs.offsets[:-1]]
    embeddings = embed_uint8_images(model, first_glyphs, device)
    return nearest_other_group(embeddings, data.groups, neighbours)


def parameter_groups(model: GlyphEncoder, weight_decay: float) -> list[dict[str, Any]]:
    decay: list[torch.nn.Parameter] = []
    no_decay: list[torch.nn.Parameter] = []
    for name, parameter in model.named_parameters():
        (no_decay if parameter.ndim <= 1 or name.endswith(".bias") else decay).append(parameter)
    return [
        {"params": decay, "weight_decay": weight_decay},
        {"params": no_decay, "weight_decay": 0.0},
    ]


def train_encoder(
    data: TrainingData,
    config: TrainingConfig,
    output_dir: Path,
    device: torch.device | None = None,
) -> dict[str, Any]:
    """Train from scratch; save ``encoder.pt`` and ``training_log.json`` in ``output_dir``."""
    device = device or torch.device("cpu")
    torch.manual_seed(config.seed)
    rng = np.random.default_rng(config.seed)
    model = GlyphEncoder(config.encoder).to(device).to(memory_format=torch.channels_last)
    loss_function = ContrastiveLoss().to(device)
    optimizer = torch.optim.AdamW(
        [
            *parameter_groups(model, config.weight_decay),
            {"params": loss_function.parameters(), "weight_decay": 0.0},
        ],
        lr=config.learning_rate,
    )
    sampler = BatchSampler(
        len(data.characters),
        config.batch_characters,
        glyph_hog_neighbours(data, config.neighbours),
        config.hard_fraction,
        config.neighbourhood_size,
        rng,
    )
    log: list[dict[str, float]] = []
    started = time.monotonic()
    step = 0
    stopped_early = False
    for step in range(config.steps):
        if config.time_budget_seconds and time.monotonic() - started > config.time_budget_seconds:
            stopped_early = True
            break
        if step > 0 and step % config.refresh_every == 0:
            sampler.update_neighbours(model_neighbours(model, data, config.neighbours, device))
        learning_rate = learning_rate_at(step, config, time.monotonic() - started)
        for group in optimizer.param_groups:
            group["lr"] = learning_rate
        batch = assemble_batch(data, sampler.sample(), config.real_probability, rng)
        count = len(batch.characters)
        images = model_input(torch.cat([batch.first_view, batch.second_view, batch.glyphs]), device)
        embeddings = model(images)
        losses = loss_function(
            embeddings[:count],
            embeddings[count : 2 * count],
            embeddings[2 * count :],
            batch.same_group.to(device),
        )
        optimizer.zero_grad(set_to_none=True)
        losses["loss"].backward()
        optimizer.step()
        if step % config.log_every == 0 or step == config.steps - 1:
            elapsed = time.monotonic() - started
            entry = {
                "step": step,
                "seconds": round(elapsed, 1),
                "learning_rate": learning_rate,
                "scale": float(loss_function.scale.detach()),
                **{name: round(float(value.detach()), 4) for name, value in losses.items()},
            }
            log.append(entry)
            print(
                f"  step {step:5d}  loss {entry['loss']:.3f}  d→g {entry['drawing_to_glyph']:.3f}  "
                f"d→d {entry['drawing_to_drawing']:.3f}  scale {entry['scale']:.1f}  "
                f"{3 * count * (step + 1) / max(elapsed, 1e-9):.0f} img/s",
                flush=True,
            )
    summary: dict[str, Any] = {
        "steps_completed": step + (0 if stopped_early else 1),
        "stopped_early": stopped_early,
        "seconds": round(time.monotonic() - started, 1),
        "config": asdict(config),
        "log": log,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    torch.save(
        {"model": model.state_dict(), "encoder_config": asdict(config.encoder)},
        output_dir / CHECKPOINT_FILE,
    )
    (output_dir / LOG_FILE).write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    return summary


def load_encoder(path: Path, device: torch.device | None = None) -> GlyphEncoder:
    from glyphsketch.model.encoder import BlockSpec

    checkpoint = torch.load(path, map_location=device or "cpu", weights_only=True)
    raw = checkpoint["encoder_config"]
    config = EncoderConfig(
        stem_channels=raw["stem_channels"],
        blocks=tuple(BlockSpec(**block) for block in raw["blocks"]),
        head_channels=raw["head_channels"],
        embedding_dim=raw["embedding_dim"],
    )
    model = GlyphEncoder(config)
    model.load_state_dict(checkpoint["model"])
    model.to(memory_format=torch.channels_last)
    model.eval()
    return model
