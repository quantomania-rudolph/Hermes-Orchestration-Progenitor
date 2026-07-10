"""Expanding-window purged splits with embargo for pairs walk-forward backtests.

Reuses the chronological expanding-window + purge/embargo pattern from
``quant_attention`` / ``lstm_optuna_vault_trader.purged_kfold``: each fold
grows the train window from index 0, holds out a fixed OOS test block, and
removes train rows in the purge zone around the test window.
"""

from __future__ import annotations

from typing import Any

import numpy as np

import config as cfg

SMOKE = bool(getattr(cfg, "SMOKE", True))

EMBARGO_BARS = 2 if SMOKE else 5
MIN_TRAIN_BARS = 28 if SMOKE else 252
TEST_BARS = 10 if SMOKE else 63
N_SPLITS = 2 if SMOKE else 5
PURGE_BARS = 5 if SMOKE else 20

FoldPair = tuple[np.ndarray, np.ndarray]
FoldList = list[FoldPair]

__all__ = [
    "EMBARGO_BARS",
    "MIN_TRAIN_BARS",
    "N_SPLITS",
    "PURGE_BARS",
    "TEST_BARS",
    "adaptive_split_params",
    "assert_purge_valid",
    "expanding_purged_splits",
    "minimum_bars_for_splits",
    "split_summary",
]


def minimum_bars_for_splits(
    n_splits: int | None = None,
    *,
    min_train_bars: int | None = None,
    test_bars: int | None = None,
    embargo_bars: int = EMBARGO_BARS,
) -> int:
    """Minimum bar count required for ``n_splits`` expanding purged folds."""
    splits = N_SPLITS if n_splits is None else n_splits
    train_min = MIN_TRAIN_BARS if min_train_bars is None else min_train_bars
    test = TEST_BARS if test_bars is None else test_bars
    if splits < 1:
        raise ValueError(f"n_splits must be >= 1, got {splits}")
    if test < 1:
        raise ValueError(f"test_bars must be >= 1, got {test}")
    stride = test + embargo_bars
    return train_min + splits * test + max(0, splits - 1) * embargo_bars


def adaptive_split_params(n_bars: int) -> dict[str, int]:
    """Downscale split parameters until folds fit the available sample."""
    n_splits = N_SPLITS
    min_train = MIN_TRAIN_BARS
    test = TEST_BARS
    embargo = EMBARGO_BARS
    purge = PURGE_BARS

    for _ in range(24):
        need = minimum_bars_for_splits(
            n_splits,
            min_train_bars=min_train,
            test_bars=test,
            embargo_bars=embargo,
        )
        if n_bars >= need:
            return {
                "n_splits": n_splits,
                "min_train_bars": min_train,
                "test_bars": test,
                "embargo_bars": embargo,
                "purge_bars": purge,
            }

        if test > 5:
            test = max(5, test // 2)
        elif min_train > 15:
            min_train = max(15, min_train // 2)
        elif n_splits > 1:
            n_splits -= 1
        elif purge > max(embargo, 1):
            purge = max(max(embargo, 1), purge // 2)
        elif embargo > 0:
            embargo = max(0, embargo - 1)
        else:
            min_train = max(10, min_train // 2)
            if n_bars < min_train + test + 1:
                break

    raise ValueError(
        f"insufficient bars ({n_bars}) for purged expanding-window splits "
        f"(need >={minimum_bars_for_splits()})"
    )


def expanding_purged_splits(
    n: int,
    *,
    n_splits: int | None = None,
    min_train_bars: int | None = None,
    test_bars: int | None = None,
    embargo_bars: int = EMBARGO_BARS,
    purge_bars: int | None = None,
) -> FoldList:
    """
    Expanding-window purged splits in chronological order.

    Fold ``k``:
      - test: ``[t_k, t_k + test_bars)``
      - train: ``[0, t_k)`` minus purge zone
        ``[t_k - purge_bars, t_k + test_bars + embargo_bars)``
    """
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")

    splits = N_SPLITS if n_splits is None else n_splits
    train_min = MIN_TRAIN_BARS if min_train_bars is None else min_train_bars
    test = TEST_BARS if test_bars is None else test_bars
    purge = PURGE_BARS if purge_bars is None else purge_bars

    if splits < 1:
        raise ValueError(f"n_splits must be >= 1, got {splits}")
    if train_min < 1:
        raise ValueError(f"min_train_bars must be >= 1, got {train_min}")
    if test < 1:
        raise ValueError(f"test_bars must be >= 1, got {test}")
    if embargo_bars < 0:
        raise ValueError(f"embargo_bars must be >= 0, got {embargo_bars}")
    if purge < 0:
        raise ValueError(f"purge_bars must be >= 0, got {purge}")

    need = minimum_bars_for_splits(
        splits,
        min_train_bars=train_min,
        test_bars=test,
        embargo_bars=embargo_bars,
    )
    if n < need:
        raise ValueError(
            f"need at least {need} bars for {splits} purged folds; got {n}"
        )

    folds: FoldList = []
    stride = test + embargo_bars
    pre_gap = max(purge, embargo_bars)

    for k in range(splits):
        test_start = train_min + k * stride
        test_end = test_start + test
        if test_end > n:
            raise ValueError(
                f"fold {k}: test window [{test_start}, {test_end}) exceeds n={n}"
            )

        test_idx = np.arange(test_start, test_end, dtype=np.int64)
        raw_train = np.arange(0, test_start, dtype=np.int64)
        train_idx = _apply_purge(
            raw_train,
            test_start=test_start,
            test_end=test_end,
            pre_gap=pre_gap,
            embargo_bars=embargo_bars,
            n=n,
        )
        if train_idx.size == 0:
            raise ValueError(f"fold {k}: purge removed all train indices")

        assert_purge_valid(
            train_idx,
            test_idx,
            embargo_bars=embargo_bars,
            pre_gap=pre_gap,
        )
        folds.append((train_idx, test_idx))

    return folds


def _apply_purge(
    train_idx: np.ndarray,
    *,
    test_start: int,
    test_end: int,
    pre_gap: int,
    embargo_bars: int,
    n: int,
) -> np.ndarray:
    purge_lo = max(0, test_start - pre_gap)
    purge_hi = min(n - 1, test_end - 1 + embargo_bars)
    if purge_lo > purge_hi:
        return train_idx
    in_zone = (train_idx >= purge_lo) & (train_idx <= purge_hi)
    return train_idx[~in_zone]


def assert_purge_valid(
    train_idx: np.ndarray,
    test_idx: np.ndarray,
    *,
    embargo_bars: int = EMBARGO_BARS,
    pre_gap: int | None = None,
) -> None:
    """Hard leakage gates for a single purged fold."""
    train = np.asarray(train_idx, dtype=np.int64)
    test = np.asarray(test_idx, dtype=np.int64)
    gap = max(PURGE_BARS, embargo_bars) if pre_gap is None else pre_gap

    if train.size == 0:
        raise AssertionError("train_idx is empty")
    if test.size == 0:
        raise AssertionError("test_idx is empty")

    overlap = np.intersect1d(train, test)
    if overlap.size > 0:
        raise AssertionError(
            f"train and test indices overlap ({overlap.size} shared rows)"
        )

    train_max = int(train.max())
    test_min = int(test.min())
    test_max = int(test.max())
    if train_max >= test_min:
        raise AssertionError(
            f"train max index {train_max} must be < test min index {test_min}"
        )

    purge_lo = max(0, test_min - gap)
    purge_hi = test_max + embargo_bars
    leaked = train[(train >= purge_lo) & (train <= purge_hi)]
    if leaked.size > 0:
        raise AssertionError(
            f"{leaked.size} train indices remain inside purge zone "
            f"[{purge_lo}, {purge_hi}]"
        )

    purge_gap = test_min - train_max - 1
    if purge_gap < gap:
        raise AssertionError(
            f"purge gap {purge_gap} bars is < required {gap}"
        )


def split_summary(
    folds: FoldList,
    *,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Lightweight manifest for audit logs."""
    entries: list[dict[str, Any]] = []
    for k, (train_idx, test_idx) in enumerate(folds):
        entries.append(
            {
                "fold": k,
                "train_count": int(train_idx.size),
                "test_count": int(test_idx.size),
                "train_idx_range": [int(train_idx.min()), int(train_idx.max())],
                "test_idx_range": [int(test_idx.min()), int(test_idx.max())],
            }
        )
    out = dict(params or {})
    out["folds"] = entries
    out["n_folds"] = len(entries)
    return out
