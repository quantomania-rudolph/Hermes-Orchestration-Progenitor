"""Purged expanding-window K-fold splits with embargo (López de Prado §8, §22.3).

Outer folds use chronological expanding train windows and fixed-length OOS test
blocks. Train indices overlapping the test label/feature window are purged;
``embargo_bars`` additional bars after each test block are removed from train.

Fold index tuples are consumed by ``optuna_tuner`` (train only) and
``backtest_pnl`` / ``trading_loop`` (test / OOS only).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import config

EMBARGO_BARS = 12

__all__ = [
    "EMBARGO_BARS",
    "assert_purge_valid",
    "backtest_fold_indices",
    "build_split_manifest",
    "fold_index_tuples",
    "minimum_bars_for_splits",
    "optuna_fold_indices",
    "purged_kfold_splits",
    "write_split_manifest",
]

FoldPair = tuple[np.ndarray, np.ndarray]
FoldList = list[FoldPair]


def minimum_bars_for_splits(
    n_splits: int | None = None,
    *,
    min_train_bars: int | None = None,
    test_bars: int | None = None,
    embargo_bars: int = EMBARGO_BARS,
) -> int:
    """Minimum sequence-bar count required for ``n_splits`` purged folds."""
    splits = config.N_SPLITS if n_splits is None else n_splits
    train_min = config.MIN_TRAIN_BARS if min_train_bars is None else min_train_bars
    test = config.TEST_BARS if test_bars is None else test_bars
    if splits < 1:
        raise ValueError(f"n_splits must be >= 1, got {splits}")
    if test < 1:
        raise ValueError(f"test_bars must be >= 1, got {test}")
    stride = test + embargo_bars
    return train_min + splits * test + max(0, splits - 1) * embargo_bars


def purged_kfold_splits(
    timestamps: np.ndarray,
    n_splits: int | None = None,
    *,
    embargo_bars: int = EMBARGO_BARS,
    min_train_bars: int | None = None,
    test_bars: int | None = None,
    lookback: int | None = None,
) -> FoldList:
    """
    Expanding-window purged K-fold splits in chronological order.

    Fold ``k``:
      - test: ``[t_k, t_k + test_bars)``
      - train: ``[0, t_k)`` minus purge zone
        ``[t_k - max(lookback, embargo_bars), t_k + test_bars + embargo_bars)``

    Parameters default from ``config`` (``N_SPLITS``, ``MIN_TRAIN_BARS``,
    ``TEST_BARS``, ``LOOKBACK``).
    """
    ts = np.asarray(timestamps)
    n = int(ts.shape[0])
    if n == 0:
        raise ValueError("timestamps is empty")
    _validate_timestamps(ts)

    splits = config.N_SPLITS if n_splits is None else n_splits
    train_min = config.MIN_TRAIN_BARS if min_train_bars is None else min_train_bars
    test = config.TEST_BARS if test_bars is None else test_bars
    lb = config.LOOKBACK if lookback is None else lookback

    if splits < 1:
        raise ValueError(f"n_splits must be >= 1, got {splits}")
    if train_min < 1:
        raise ValueError(f"min_train_bars must be >= 1, got {train_min}")
    if test < 1:
        raise ValueError(f"test_bars must be >= 1, got {test}")
    if lb < 1:
        raise ValueError(f"lookback must be >= 1, got {lb}")
    if embargo_bars < 0:
        raise ValueError(f"embargo_bars must be >= 0, got {embargo_bars}")

    need = minimum_bars_for_splits(
        splits,
        min_train_bars=train_min,
        test_bars=test,
        embargo_bars=embargo_bars,
    )
    if n < need:
        raise ValueError(
            f"need at least {need} bars for {splits} purged folds "
            f"(min_train_bars={train_min}, test_bars={test}, "
            f"embargo_bars={embargo_bars}); got {n}"
        )

    folds: FoldList = []
    stride = test + embargo_bars

    for k in range(splits):
        test_start = train_min + k * stride
        test_end = test_start + test
        if test_end > n:
            raise ValueError(
                f"fold {k}: test window [{test_start}, {test_end}) exceeds "
                f"available bars (n={n})"
            )

        test_idx = np.arange(test_start, test_end, dtype=np.int64)
        raw_train = np.arange(0, test_start, dtype=np.int64)
        train_idx = _apply_purge(
            raw_train,
            test_start=test_start,
            test_end=test_end,
            lookback=lb,
            embargo_bars=embargo_bars,
            n=n,
        )

        if train_idx.size == 0:
            raise ValueError(f"fold {k}: purge removed all train indices")

        assert_purge_valid(
            train_idx,
            test_idx,
            ts,
            embargo_bars=embargo_bars,
            lookback=lb,
        )
        folds.append((train_idx, test_idx))

    return folds


def _apply_purge(
    train_idx: np.ndarray,
    *,
    test_start: int,
    test_end: int,
    lookback: int,
    embargo_bars: int,
    n: int,
) -> np.ndarray:
    """Drop train rows whose bar index falls in the purge + embargo zone."""
    pre_gap = max(lookback, embargo_bars)
    purge_lo = max(0, test_start - pre_gap)
    purge_hi = min(n - 1, test_end - 1 + embargo_bars)
    if purge_lo > purge_hi:
        return train_idx
    in_zone = (train_idx >= purge_lo) & (train_idx <= purge_hi)
    return train_idx[~in_zone]


def assert_purge_valid(
    train_idx: np.ndarray,
    test_idx: np.ndarray,
    timestamps: np.ndarray,
    *,
    embargo_bars: int = EMBARGO_BARS,
    lookback: int | None = None,
) -> None:
    """
    Hard leakage gates for a single purged fold (invariant L8).

    Raises ``AssertionError`` when train/test overlap, ordering is violated,
    purge/embargo gaps are insufficient, or label windows overlap.
    """
    ts = np.asarray(timestamps)
    train = np.asarray(train_idx, dtype=np.int64)
    test = np.asarray(test_idx, dtype=np.int64)
    lb = config.LOOKBACK if lookback is None else lookback

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

    train_max_ts = _ts_value(ts, train_max)
    test_min_ts = _ts_value(ts, test_min)
    if train_max_ts >= test_min_ts:
        raise AssertionError(
            "train max bar_end must be strictly before test min bar_end"
        )

    pre_gap = max(lb, embargo_bars)
    purge_lo = max(0, test_min - pre_gap)
    purge_hi = test_max + embargo_bars
    leaked = train[(train >= purge_lo) & (train <= purge_hi)]
    if leaked.size > 0:
        raise AssertionError(
            f"{leaked.size} train indices remain inside purge zone "
            f"[{purge_lo}, {purge_hi}]"
        )

    purge_gap = test_min - train_max - 1
    if purge_gap < pre_gap:
        raise AssertionError(
            f"purge gap {purge_gap} bars between train and test is < "
            f"required {pre_gap} (max(lookback={lb}, embargo={embargo_bars}))"
        )

    _assert_no_label_window_overlap(train, test)

    if embargo_bars > 0:
        post_test_lo = test_max + 1
        post_test_hi = test_max + embargo_bars
        post_embargo = train[
            (train >= post_test_lo) & (train <= post_test_hi)
        ]
        if post_embargo.size > 0:
            raise AssertionError(
                f"{post_embargo.size} train indices inside post-test embargo "
                f"[{post_test_lo}, {post_test_hi}]"
            )

        embargo_cutoff = _embargo_cutoff(ts, test_min, pre_gap)
        if train_max_ts >= embargo_cutoff:
            raise AssertionError(
                f"train max bar_end {train_max_ts} must be < "
                f"test min bar_end minus {pre_gap} bars ({embargo_cutoff})"
            )


def _assert_no_label_window_overlap(
    train_idx: np.ndarray,
    test_idx: np.ndarray,
) -> None:
    """Label at ``i`` uses return through bar ``i+1``; forbid overlapping windows."""
    test_min = int(test_idx.min())
    test_max = int(test_idx.max())
    for i in train_idx:
        label_end = int(i) + 1
        if test_min <= label_end <= test_max:
            raise AssertionError(
                f"train label window for index {i} overlaps test block "
                f"[{test_min}, {test_max}]"
            )


def _ts_value(ts: np.ndarray, idx: int) -> Any:
    val = ts[idx]
    if isinstance(val, (np.datetime64, pd.Timestamp)):
        return pd.Timestamp(val)
    return val


def _is_datetime_array(ts: np.ndarray) -> bool:
    if np.issubdtype(ts.dtype, np.datetime64):
        return True
    sample = ts.flat[0]
    return isinstance(sample, (pd.Timestamp, np.datetime64))


def _validate_timestamps(ts: np.ndarray) -> None:
    """Require non-decreasing bar_end timestamps (invariant L8)."""
    if ts.shape[0] < 2:
        return
    if _is_datetime_array(ts):
        t0 = pd.Timestamp(_ts_value(ts, 0))
        for i in range(1, ts.shape[0]):
            ti = pd.Timestamp(_ts_value(ts, i))
            if ti < t0:
                raise ValueError(
                    f"timestamps must be non-decreasing; index {i - 1}={t0} > index {i}={ti}"
                )
            t0 = ti
        return
    diffs = np.diff(np.asarray(ts, dtype=np.float64))
    if np.any(diffs < 0):
        bad = int(np.argmax(diffs < 0))
        raise ValueError(
            "timestamps must be non-decreasing; "
            f"index {bad}={ts[bad]} > index {bad + 1}={ts[bad + 1]}"
        )


def _bar_step(ts: np.ndarray) -> pd.Timedelta:
    """Smallest positive bar spacing for embargo bar_end arithmetic (§8.5)."""
    if ts.shape[0] < 2:
        return pd.Timedelta(minutes=5)
    deltas: list[pd.Timedelta] = []
    for i in range(1, min(ts.shape[0], 8)):
        t0 = pd.Timestamp(_ts_value(ts, i - 1))
        t1 = pd.Timestamp(_ts_value(ts, i))
        delta = t1 - t0
        if delta > pd.Timedelta(0):
            deltas.append(delta)
    if not deltas:
        return pd.Timedelta(minutes=5)
    return min(deltas)


def _embargo_cutoff(ts: np.ndarray, test_min: int, embargo_bars: int) -> Any:
    """``test_min_bar_end - embargo_bars`` in timestamp or index units."""
    test_min_ts = _ts_value(ts, test_min)
    if isinstance(test_min_ts, pd.Timestamp):
        return test_min_ts - embargo_bars * _bar_step(ts)
    return test_min_ts - embargo_bars


def fold_index_tuples(
    timestamps: np.ndarray,
    **kwargs: Any,
) -> FoldList:
    """(train_idx, test_idx) tuples per fold — shared by Optuna and backtest."""
    return purged_kfold_splits(timestamps, **kwargs)


def optuna_fold_indices(
    timestamps: np.ndarray,
    **kwargs: Any,
) -> list[np.ndarray]:
    """Train index arrays per fold for Optuna / inner-val tuning (never OOS test)."""
    return [train for train, _ in fold_index_tuples(timestamps, **kwargs)]


def backtest_fold_indices(
    timestamps: np.ndarray,
    **kwargs: Any,
) -> list[np.ndarray]:
    """OOS test index arrays per fold for backtest / trading loop."""
    return [test for _, test in fold_index_tuples(timestamps, **kwargs)]


def build_split_manifest(
    timestamps: np.ndarray,
    folds: FoldList | None = None,
    **split_kwargs: Any,
) -> dict[str, Any]:
    """Audit manifest with per-fold bar_end ranges and index counts."""
    ts = np.asarray(timestamps)
    if folds is None:
        folds = purged_kfold_splits(ts, **split_kwargs)

    embargo_bars = split_kwargs.get("embargo_bars", EMBARGO_BARS)
    min_train_bars = split_kwargs.get("min_train_bars", config.MIN_TRAIN_BARS)
    test_bars = split_kwargs.get("test_bars", config.TEST_BARS)
    n_splits = split_kwargs.get("n_splits", config.N_SPLITS)
    lookback = split_kwargs.get("lookback", config.LOOKBACK)

    fold_entries: list[dict[str, Any]] = []
    for k, (train_idx, test_idx) in enumerate(folds):
        fold_entries.append(
            {
                "fold": k,
                "train_count": int(train_idx.size),
                "test_count": int(test_idx.size),
                "train_idx_range": [int(train_idx.min()), int(train_idx.max())],
                "test_idx_range": [int(test_idx.min()), int(test_idx.max())],
                "train_bar_end_min": _iso(_ts_value(ts, int(train_idx.min()))),
                "train_bar_end_max": _iso(_ts_value(ts, int(train_idx.max()))),
                "test_bar_end_min": _iso(_ts_value(ts, int(test_idx.min()))),
                "test_bar_end_max": _iso(_ts_value(ts, int(test_idx.max()))),
            }
        )

    return {
        "n_splits": n_splits,
        "min_train_bars": min_train_bars,
        "test_bars": test_bars,
        "embargo_bars": embargo_bars,
        "lookback": lookback,
        "total_bars": int(ts.shape[0]),
        "folds": fold_entries,
    }


def write_split_manifest(
    path: str | Path,
    timestamps: np.ndarray,
    folds: FoldList | None = None,
    **split_kwargs: Any,
) -> dict[str, Any]:
    """Write ``split_manifest.json`` and return the manifest dict."""
    manifest = build_split_manifest(timestamps, folds=folds, **split_kwargs)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _iso(val: Any) -> str:
    return pd.Timestamp(val).isoformat()
