"""LSTM directional trader with residual skip and partial forgetting (§7).

Architecture: 1–2 layer ``batch_first`` LSTM, inter-layer dropout, optional
residual skip from the last input timestep, Partial Forgetting Gate, and a
linear head regressing ``next_return``.
"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

import config
from partial_forgetting import PFGMode, PartialForgettingGate, reset_lstm_hidden

LossName = Literal["mse", "huber", "bce"]
_SEED = 42
_GRAD_CLIP = 1.0

__all__ = [
    "LSTMTrader",
    "LossName",
    "build_model",
    "train_fold",
]


class LSTMTrader(nn.Module):
    """
    Sequence regressor for ``next_return``.

    Parameters
    ----------
    n_features
        Input feature dimension per timestep.
    hidden_h1, hidden_h2
        LSTM hidden sizes; layer 2 is omitted when ``n_layers == 1``.
    n_layers
        Number of stacked LSTM layers (1 or 2).
    dropout_l1, dropout_l2
        Dropout applied to layer-1 / layer-2 outputs (not after the linear head).
    use_skip
        When True, project ``x[:, -1, :]`` and add before PFG.
    pfg_mode
        Partial forgetting mode passed to :class:`PartialForgettingGate`.
    fold_reset
        When True, callers should invoke ``reset_lstm_hidden`` at fold
        boundaries; forward always initializes LSTM state to zero per batch.
    """

    def __init__(
        self,
        n_features: int,
        *,
        hidden_h1: int = 64,
        hidden_h2: int = 32,
        n_layers: int = 1,
        dropout_l1: float = 0.2,
        dropout_l2: float = 0.1,
        use_skip: bool = True,
        pfg_mode: PFGMode = "learned",
        fold_reset: bool = False,
    ) -> None:
        super().__init__()
        if n_features < 1:
            raise ValueError(f"n_features must be >= 1, got {n_features}")
        if n_layers not in (1, 2):
            raise ValueError(f"n_layers must be 1 or 2, got {n_layers}")

        self.n_features = n_features
        self.hidden_h1 = hidden_h1
        self.hidden_h2 = hidden_h2 if n_layers == 2 else 0
        self.n_layers = n_layers
        self.use_skip = use_skip
        self.fold_reset = fold_reset
        self.hidden_out = hidden_h2 if n_layers == 2 else hidden_h1

        self.lstm1 = nn.LSTM(
            input_size=n_features,
            hidden_size=hidden_h1,
            num_layers=1,
            batch_first=True,
        )
        self.dropout1 = nn.Dropout(dropout_l1)

        self.lstm2: nn.LSTM | None = None
        self.dropout2: nn.Dropout | None = None
        if n_layers == 2:
            if hidden_h2 < 1:
                raise ValueError("hidden_h2 must be >= 1 when n_layers == 2")
            self.lstm2 = nn.LSTM(
                input_size=hidden_h1,
                hidden_size=hidden_h2,
                num_layers=1,
                batch_first=True,
            )
            self.dropout2 = nn.Dropout(dropout_l2)

        self.skip_proj = (
            nn.Linear(n_features, self.hidden_out) if use_skip else None
        )
        self.pfg = PartialForgettingGate(
            self.hidden_out,
            mode="fold_reset" if fold_reset else pfg_mode,
        )
        self.head = nn.Linear(self.hidden_out, 1)
        self._fold_hidden: tuple[torch.Tensor, ...] | None = None

    def reset_fold_hidden(self) -> None:
        """Clear cached recurrent state at a purged fold boundary (invariant L7)."""
        self._fold_hidden = None

    def forward(
        self,
        x: torch.Tensor,
        *,
        epoch: int = 0,
        max_epochs: int = 1,
    ) -> torch.Tensor:
        if x.ndim != 3:
            raise ValueError(f"expected input shape (batch, seq, features), got {x.shape}")
        if x.shape[-1] != self.n_features:
            raise ValueError(
                f"expected {self.n_features} features, got {x.shape[-1]}"
            )

        batch_size = x.size(0)
        h0, c0 = _zero_lstm_state(self.lstm1, batch_size, x.device)
        out1, _ = self.lstm1(x, (h0, c0))
        out1 = self.dropout1(out1)

        if self.lstm2 is not None and self.dropout2 is not None:
            h0_2, c0_2 = _zero_lstm_state(self.lstm2, batch_size, x.device)
            out2, _ = self.lstm2(out1, (h0_2, c0_2))
            out2 = self.dropout2(out2)
            h_lstm = out2[:, -1, :]
        else:
            h_lstm = out1[:, -1, :]

        if self.skip_proj is not None:
            h_skip = self.skip_proj(x[:, -1, :])
        else:
            h_skip = torch.zeros_like(h_lstm)

        h_out = self.pfg(h_lstm, h_skip, epoch=epoch, max_epochs=max_epochs)
        return self.head(h_out).squeeze(-1)


def build_model(n_features: int, **hyperparams: Any) -> LSTMTrader:
    """Construct :class:`LSTMTrader` from Optuna / checkpoint hyperparameters."""
    params = dict(hyperparams)
    n_layers = int(params.pop("n_layers", 1))
    hidden_h2 = int(params.get("hidden_h2", 32))

    if hidden_h2 < 1:
        n_layers = 1
        params["hidden_h2"] = 0
    elif n_layers == 1:
        params["hidden_h2"] = 0

    pfg_mode = params.get("pfg_mode")
    if pfg_mode == "fold_reset" or params.get("fold_reset"):
        params["fold_reset"] = True
        params.pop("pfg_mode", None)

    return LSTMTrader(n_features, n_layers=n_layers, **params)


def train_fold(
    model: LSTMTrader,
    train_loader: DataLoader,
    val_loader: DataLoader,
    *,
    epochs: int | None = None,
    lr: float = 1e-3,
    weight_decay: float = 1e-5,
    loss: LossName = "huber",
    early_stop_patience: int | None = None,
    device: torch.device | None = None,
) -> dict[str, float]:
    """
    Train one fold with AdamW, gradient clipping, and early stopping.

    Returns ``train_loss``, ``val_loss``, and ``best_epoch`` (1-based) for the
    best validation checkpoint. Uses seed 42 and runs CPU-safe by default.
    """
    torch.manual_seed(_SEED)
    np.random.seed(_SEED)

    n_epochs = config.EPOCHS if epochs is None else epochs
    patience = (
        (3 if config.SMOKE else 5) if early_stop_patience is None else early_stop_patience
    )
    dev = device or torch.device("cpu")
    model = model.to(dev)
    if model.fold_reset:
        reset_lstm_hidden(model)

    criterion = _build_loss(loss)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)

    best_val = float("inf")
    best_epoch = 0
    best_state: dict[str, Any] | None = None
    stale = 0
    last_train_loss = float("nan")

    for epoch in range(n_epochs):
        model.train()
        train_losses: list[float] = []

        for xb, yb in train_loader:
            xb = xb.to(dev)
            yb = yb.to(dev)
            optimizer.zero_grad(set_to_none=True)
            preds = model(xb, epoch=epoch, max_epochs=n_epochs)
            batch_loss = criterion(preds, yb)
            batch_loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), _GRAD_CLIP)
            optimizer.step()
            train_losses.append(float(batch_loss.detach().cpu()))

        last_train_loss = float(np.mean(train_losses)) if train_losses else float("nan")
        val_loss = _eval_loss(model, val_loader, criterion, dev, epoch, n_epochs)

        if val_loss < best_val:
            best_val = val_loss
            best_epoch = epoch + 1
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            stale = 0
        else:
            stale += 1
            if stale >= patience:
                break

    if best_state is not None:
        model.load_state_dict(best_state)

    return {
        "train_loss": last_train_loss,
        "val_loss": best_val,
        "best_epoch": float(best_epoch),
    }


def make_loaders(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    *,
    batch_size: int = 64,
) -> tuple[DataLoader, DataLoader]:
    """Build train/val loaders for sequence tensors (helper for tuners/tests)."""
    train_ds = TensorDataset(
        torch.from_numpy(np.array(X_train, dtype=np.float32, copy=True)),
        torch.from_numpy(np.array(y_train, dtype=np.float32, copy=True)),
    )
    val_ds = TensorDataset(
        torch.from_numpy(np.array(X_val, dtype=np.float32, copy=True)),
        torch.from_numpy(np.array(y_val, dtype=np.float32, copy=True)),
    )
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)
    return train_loader, val_loader


def _zero_lstm_state(
    lstm: nn.LSTM,
    batch_size: int,
    device: torch.device,
) -> tuple[torch.Tensor, torch.Tensor]:
    n_layer = lstm.num_layers
    hidden = lstm.hidden_size
    h0 = torch.zeros(n_layer, batch_size, hidden, device=device)
    c0 = torch.zeros(n_layer, batch_size, hidden, device=device)
    return h0, c0


def _build_loss(name: LossName) -> nn.Module:
    if name == "mse":
        return nn.MSELoss()
    if name == "huber":
        return nn.SmoothL1Loss()
    if name == "bce":
        return nn.BCEWithLogitsLoss()
    raise ValueError(f"unsupported loss: {name}")


@torch.no_grad()
def _eval_loss(
    model: LSTMTrader,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
    epoch: int,
    max_epochs: int,
) -> float:
    model.eval()
    reset_lstm_hidden(model)
    losses: list[float] = []

    for xb, yb in loader:
        xb = xb.to(device)
        yb = yb.to(device)
        preds = model(xb, epoch=epoch, max_epochs=max_epochs)
        losses.append(float(criterion(preds, yb).detach().cpu()))

    return float(np.mean(losses)) if losses else float("inf")
