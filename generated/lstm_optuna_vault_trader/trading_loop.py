"""OOS trading loop: regression predictions → positions with costs (§9).

Maps LSTM ``y_hat`` on outer test folds only to positions in ``{-1, 0, 1}``,
applies deadband churn control, and computes bar-level strategy returns with
1 bp slippage plus 0.5 bp spread proxy per position change. Fold boundaries
reset carried position so OOS blocks do not share execution state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

DEFAULT_SLIPPAGE_BPS = 1.0
DEFAULT_SPREAD_BPS = 0.5
DEFAULT_DEADBAND = 0.0001

PositionMode = Literal["sign", "threshold", "prob"]

__all__ = [
    "DEFAULT_DEADBAND",
    "DEFAULT_SLIPPAGE_BPS",
    "DEFAULT_SPREAD_BPS",
    "OOSFoldBatch",
    "PositionMode",
    "TradingLoopResult",
    "compute_strategy_returns",
    "concatenate_oos_batches",
    "position_changes",
    "predictions_to_positions",
    "run_trading_loop",
    "run_trading_loop_from_batches",
]


@dataclass(frozen=True)
class OOSFoldBatch:
    """OOS predictions for one purged outer fold (test indices only)."""

    fold_id: int
    bar_idx: np.ndarray
    y_hat: np.ndarray
    next_return: np.ndarray
    timestamps: np.ndarray
    y_true: np.ndarray | None = None


@dataclass
class TradingLoopResult:
    """Per-bar trading loop outputs aligned to OOS prediction rows."""

    positions: np.ndarray
    strategy_returns: np.ndarray
    gross_returns: np.ndarray
    costs: np.ndarray
    timestamps: np.ndarray | None = None
    fold_ids: np.ndarray | None = None
    bar_indices: np.ndarray | None = None


def predictions_to_positions(
    y_hat: np.ndarray,
    *,
    mode: PositionMode = "threshold",
    threshold: float = 0.0,
    deadband: float = DEFAULT_DEADBAND,
    allow_short: bool = True,
) -> np.ndarray:
    """
    Map regression (or probability) predictions to discrete positions.

    Returns an int8 array in ``{-1, 0, 1}``. ``abs(y_hat) < deadband`` is
    always flat to reduce churn. ``threshold`` mode uses ``±threshold`` bands;
    ``sign`` ignores ``threshold``; ``prob`` treats ``y_hat`` as an up-probability
    with ``threshold`` as the neutral level (default 0.5 when ``threshold=0``).
    """
    pred = np.asarray(y_hat, dtype=np.float64)
    if pred.ndim != 1:
        raise ValueError(f"y_hat must be 1-D, got shape {pred.shape}")

    positions = np.zeros(pred.shape[0], dtype=np.int8)

    if mode == "sign":
        flat = np.abs(pred) < deadband
        positions[pred > deadband] = 1
        positions[pred < -deadband] = -1
    elif mode == "threshold":
        flat = np.abs(pred) < deadband
        positions[(pred > threshold) & ~flat] = 1
        positions[(pred < -threshold) & ~flat] = -1
    elif mode == "prob":
        neutral = threshold if threshold != 0.0 else 0.5
        flat = np.abs(pred - neutral) < deadband
        positions[pred > neutral + deadband] = 1
        positions[pred < neutral - deadband] = -1
    else:
        raise ValueError(f"unsupported mode: {mode}")

    positions[flat] = 0
    if not allow_short:
        positions = np.clip(positions, 0, 1)

    return positions


def position_changes(
    positions: np.ndarray,
    fold_ids: np.ndarray | None = None,
) -> np.ndarray:
    """
    Absolute position change per bar, resetting to flat at fold boundaries.

    When ``fold_ids`` is provided, the prior position is treated as zero at the
    first bar of each fold so OOS blocks do not inherit execution state.
    """
    pos = np.asarray(positions, dtype=np.float64)
    if pos.ndim != 1:
        raise ValueError(f"positions must be 1-D, got shape {pos.shape}")

    if fold_ids is None:
        return np.abs(np.diff(pos, prepend=0.0))

    folds = np.asarray(fold_ids)
    if folds.shape[0] != pos.shape[0]:
        raise ValueError("fold_ids length must match positions length")

    changes = np.zeros(pos.shape[0], dtype=np.float64)
    prev_pos = 0.0
    prev_fold = folds[0]
    for i in range(pos.shape[0]):
        if folds[i] != prev_fold:
            prev_pos = 0.0
            prev_fold = folds[i]
        changes[i] = abs(pos[i] - prev_pos)
        prev_pos = pos[i]
    return changes


def compute_strategy_returns(
    positions: np.ndarray,
    next_returns: np.ndarray,
    *,
    fold_ids: np.ndarray | None = None,
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS,
    spread_bps: float = DEFAULT_SPREAD_BPS,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Bar-level strategy returns after transaction costs (§9.3).

    ``strategy_return = position * next_return - cost_rate * abs(position_change)``
    with ``cost_rate = (slippage_bps + spread_bps) / 10_000``.
    """
    pos = np.asarray(positions, dtype=np.float64)
    rets = np.asarray(next_returns, dtype=np.float64)
    if pos.shape != rets.shape:
        raise ValueError(
            f"positions and next_returns must share shape; "
            f"got {pos.shape} vs {rets.shape}"
        )

    gross = pos * rets
    cost_rate = (slippage_bps + spread_bps) / 10_000.0
    changes = position_changes(pos, fold_ids=fold_ids)
    costs = cost_rate * changes
    strategy = gross - costs
    return strategy, gross, costs


def concatenate_oos_batches(
    batches: list[OOSFoldBatch],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Concatenate per-fold OOS batches in chronological order.

    Validates disjoint bar indices across folds and monotonic timestamps.
    Returns ``(y_hat, next_return, timestamps, fold_ids, bar_idx)``.
    """
    if not batches:
        raise ValueError("batches is empty")

    ordered = sorted(batches, key=lambda b: int(b.fold_id))
    seen_idx: set[int] = set()
    parts_hat: list[np.ndarray] = []
    parts_ret: list[np.ndarray] = []
    parts_ts: list[np.ndarray] = []
    parts_fold: list[np.ndarray] = []
    parts_bar: list[np.ndarray] = []

    for batch in ordered:
        bar_idx = np.asarray(batch.bar_idx, dtype=np.int64)
        y_hat = np.asarray(batch.y_hat, dtype=np.float64)
        next_ret = np.asarray(batch.next_return, dtype=np.float64)
        ts = np.asarray(batch.timestamps)

        n = bar_idx.shape[0]
        if y_hat.shape[0] != n or next_ret.shape[0] != n or ts.shape[0] != n:
            raise ValueError(
                f"fold {batch.fold_id}: bar_idx, y_hat, next_return, timestamps "
                f"must share length; got {n}, {y_hat.shape[0]}, "
                f"{next_ret.shape[0]}, {ts.shape[0]}"
            )

        overlap = set(bar_idx.tolist()) & seen_idx
        if overlap:
            raise ValueError(
                f"fold {batch.fold_id}: bar indices overlap prior OOS folds "
                f"({len(overlap)} shared rows)"
            )
        seen_idx.update(bar_idx.tolist())

        parts_hat.append(y_hat)
        parts_ret.append(next_ret)
        parts_ts.append(ts)
        parts_fold.append(np.full(n, int(batch.fold_id), dtype=np.int64))
        parts_bar.append(bar_idx)

    y_hat = np.concatenate(parts_hat)
    next_return = np.concatenate(parts_ret)
    timestamps = np.concatenate(parts_ts)
    fold_ids = np.concatenate(parts_fold)
    bar_idx = np.concatenate(parts_bar)

    if bar_idx.shape[0] >= 2:
        order = np.argsort(bar_idx, kind="stable")
        if not np.array_equal(bar_idx[order], bar_idx):
            y_hat = y_hat[order]
            next_return = next_return[order]
            timestamps = timestamps[order]
            fold_ids = fold_ids[order]
            bar_idx = bar_idx[order]
        if np.any(np.diff(bar_idx) <= 0):
            raise ValueError("concatenated bar_idx must be strictly increasing")

    return y_hat, next_return, timestamps, fold_ids, bar_idx


def run_trading_loop(
    y_hat: np.ndarray,
    next_returns: np.ndarray,
    *,
    timestamps: np.ndarray | None = None,
    fold_ids: np.ndarray | None = None,
    bar_indices: np.ndarray | None = None,
    mode: PositionMode = "threshold",
    threshold: float = 0.0,
    deadband: float = DEFAULT_DEADBAND,
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS,
    spread_bps: float = DEFAULT_SPREAD_BPS,
    allow_short: bool = True,
) -> TradingLoopResult:
    """
    Full OOS trading loop: predictions → positions → cost-adjusted returns.

    Intended for concatenated outer-test predictions only (invariant L5).
    """
    positions = predictions_to_positions(
        y_hat,
        mode=mode,
        threshold=threshold,
        deadband=deadband,
        allow_short=allow_short,
    )
    strategy, gross, costs = compute_strategy_returns(
        positions,
        next_returns,
        fold_ids=fold_ids,
        slippage_bps=slippage_bps,
        spread_bps=spread_bps,
    )
    return TradingLoopResult(
        positions=positions,
        strategy_returns=strategy,
        gross_returns=gross,
        costs=costs,
        timestamps=timestamps,
        fold_ids=fold_ids,
        bar_indices=bar_indices,
    )


def run_trading_loop_from_batches(
    batches: list[OOSFoldBatch],
    *,
    mode: PositionMode = "threshold",
    threshold: float = 0.0,
    deadband: float = DEFAULT_DEADBAND,
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS,
    spread_bps: float = DEFAULT_SPREAD_BPS,
    allow_short: bool = True,
) -> TradingLoopResult:
    """
    Run the trading loop on per-fold OOS batches only (invariant L5).

    Concatenates outer-test predictions, then maps to positions and
    cost-adjusted returns with fold-boundary execution resets.
    """
    y_hat, next_returns, timestamps, fold_ids, bar_indices = concatenate_oos_batches(
        batches
    )
    return run_trading_loop(
        y_hat,
        next_returns,
        timestamps=timestamps,
        fold_ids=fold_ids,
        bar_indices=bar_indices,
        mode=mode,
        threshold=threshold,
        deadband=deadband,
        slippage_bps=slippage_bps,
        spread_bps=spread_bps,
        allow_short=allow_short,
    )
