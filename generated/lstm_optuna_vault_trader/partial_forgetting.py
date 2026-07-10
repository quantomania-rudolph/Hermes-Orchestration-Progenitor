"""Partial Forgetting Gate (PFG) for LSTM hidden-state blending.

Implements explicit control over persistence of recurrent state vs. a feedforward
skip path (§7.2). ``fold_reset`` policy zeroes LSTM hidden buffers at purged
fold boundaries (invariant L7).
"""

from __future__ import annotations

from typing import Literal

import torch
import torch.nn as nn

PFGMode = Literal["learned", "scheduled", "fold_reset"]

__all__ = [
    "PFGMode",
    "PartialForgettingGate",
    "reset_lstm_hidden",
]


class PartialForgettingGate(nn.Module):
    """
    Blend recurrent and skip representations.

    ``h_out = alpha * h_lstm + (1 - alpha) * h_skip`` where
    ``alpha = sigmoid(W @ h_lstm + b)`` (per hidden unit).

    Modes
    -----
    learned
        Alpha is fully learned via backprop.
    scheduled
        Alpha is annealed from 0.9 toward 0.5 over training epochs while
        retaining the learned gate shape.
    fold_reset
        Same gate as ``learned``; caller must invoke ``reset_lstm_hidden`` at
        each purged fold boundary so recurrent memory does not leak across folds.
    """

    def __init__(
        self,
        hidden_dim: int,
        *,
        mode: PFGMode = "learned",
    ) -> None:
        super().__init__()
        if hidden_dim < 1:
            raise ValueError(f"hidden_dim must be >= 1, got {hidden_dim}")
        if mode not in ("learned", "scheduled", "fold_reset"):
            raise ValueError(f"unsupported pfg mode: {mode}")

        self.hidden_dim = hidden_dim
        self.mode: PFGMode = mode
        self.alpha_proj = nn.Linear(hidden_dim, hidden_dim)

    def forward(
        self,
        h_lstm: torch.Tensor,
        h_skip: torch.Tensor,
        *,
        epoch: int = 0,
        max_epochs: int = 1,
    ) -> torch.Tensor:
        if h_lstm.shape != h_skip.shape:
            raise ValueError(
                f"h_lstm shape {tuple(h_lstm.shape)} != h_skip shape {tuple(h_skip.shape)}"
            )
        if h_lstm.shape[-1] != self.hidden_dim:
            raise ValueError(
                f"expected hidden_dim {self.hidden_dim}, got {h_lstm.shape[-1]}"
            )

        alpha = torch.sigmoid(self.alpha_proj(h_lstm))

        if self.mode == "scheduled":
            progress = epoch / max(max_epochs - 1, 1)
            schedule = 0.9 - 0.4 * progress
            alpha = schedule * alpha + (1.0 - schedule) * 0.5

        return alpha * h_lstm + (1.0 - alpha) * h_skip


def reset_lstm_hidden(module: nn.Module) -> None:
    """
    Zero LSTM hidden/cell buffers at a purged fold boundary.

    Dispatches to ``reset_fold_hidden()`` when present (``LSTMTrader``). Also
    clears any optional ``_fold_hidden`` / ``hidden`` / ``cell`` tensors
    registered on submodules for streaming inference paths.
    """
    if hasattr(module, "reset_fold_hidden"):
        module.reset_fold_hidden()

    for child in module.modules():
        fold_buf = getattr(child, "_fold_hidden", None)
        if isinstance(fold_buf, tuple):
            child._fold_hidden = tuple(
                torch.zeros_like(t) if isinstance(t, torch.Tensor) else t
                for t in fold_buf
            )
        for attr in ("hidden", "cell", "_hidden", "_cell"):
            state = getattr(child, attr, None)
            if isinstance(state, torch.Tensor):
                state.zero_()
        hx = getattr(child, "hx", None)
        if isinstance(hx, tuple):
            for t in hx:
                if isinstance(t, torch.Tensor):
                    t.zero_()
