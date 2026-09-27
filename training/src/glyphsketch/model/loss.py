"""Contrastive loss with confusable-group masking.

Each batch holds B distinct characters with two synthetic drawings (views) and one glyph
render each. Three InfoNCE terms pull matching pairs together:

* drawing → glyph and glyph → drawing (what index option (a), glyph embeddings, needs);
* drawing → other drawing of the same character (what index option (b), prototypes
  averaged over synthetic drawings, needs).

Characters in the same confusable group look identical (Latin A, Greek Α), so their pairs
are removed from the negatives (PLAN.md, section 1, change 3): their logits are masked
before the softmax. Hard negatives come from the batch composition (see ``data``).
"""

import torch
from torch import nn
from torch.nn import functional

MASKED_LOGIT = -1e4


def masked_info_nce(
    queries: torch.Tensor, keys: torch.Tensor, scale: torch.Tensor, same_group: torch.Tensor
) -> torch.Tensor:
    """InfoNCE of ``queries[i]`` against ``keys`` with positive ``keys[i]``.

    ``same_group[i, j]`` is True when characters i and j are distinct members of one
    confusable group; those logits are excluded. Diagonal entries must be False.
    """
    logits = scale * queries @ keys.T
    logits = logits.masked_fill(same_group, MASKED_LOGIT)
    targets = torch.arange(len(queries), device=queries.device)
    return functional.cross_entropy(logits, targets)


class ContrastiveLoss(nn.Module):
    def __init__(self, initial_temperature: float = 0.07, max_scale: float = 100.0) -> None:
        super().__init__()
        self.log_scale = nn.Parameter(torch.tensor(float(1 / initial_temperature)).log())
        self.max_scale = max_scale

    @property
    def scale(self) -> torch.Tensor:
        return self.log_scale.exp().clamp(max=self.max_scale)

    def forward(
        self,
        first_view: torch.Tensor,
        second_view: torch.Tensor,
        glyphs: torch.Tensor,
        same_group: torch.Tensor,
    ) -> dict[str, torch.Tensor]:
        scale = self.scale
        drawing_to_glyph = masked_info_nce(first_view, glyphs, scale, same_group)
        glyph_to_drawing = masked_info_nce(glyphs, first_view, scale, same_group)
        drawing_to_drawing = masked_info_nce(first_view, second_view, scale, same_group)
        total = (drawing_to_glyph + glyph_to_drawing) / 2 + drawing_to_drawing
        return {
            "loss": total,
            "drawing_to_glyph": drawing_to_glyph.detach(),
            "glyph_to_drawing": glyph_to_drawing.detach(),
            "drawing_to_drawing": drawing_to_drawing.detach(),
        }
