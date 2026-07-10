"""Expanding-window walk-forward index splits for sklearn forecast backtests."""

from __future__ import annotations

import numpy as np

try:
    from config import MIN_TRAIN_ROWS, STEP_ROWS, TEST_ROWS
except ImportError:  # pragma: no cover - package import when run as module
    from .config import MIN_TRAIN_ROWS, STEP_ROWS, TEST_ROWS

__all__ = ["expanding_window_splits"]

FoldList = list[tuple[np.ndarray, np.ndarray]]


def expanding_window_splits(
    n: int,
    *,
    min_train: int = MIN_TRAIN_ROWS,
    test: int = TEST_ROWS,
    step: int = STEP_ROWS,
) -> FoldList:
    """
    Generate chronological expanding-window train/test index folds.

    Fold ``k`` uses:
      - train indices ``[0, test_start)``
      - test indices ``[test_start, test_start + test)``

    where ``test_start = min_train + k * step`` and advances until the test
    window would extend past ``n``.
    """
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    if min_train < 1:
        raise ValueError(f"min_train must be >= 1, got {min_train}")
    if test < 1:
        raise ValueError(f"test must be >= 1, got {test}")
    if step < 1:
        raise ValueError(f"step must be >= 1, got {step}")
    if n < min_train + test:
        raise ValueError(
            f"need at least {min_train + test} rows for one fold "
            f"(min_train={min_train}, test={test}); got {n}"
        )

    folds: FoldList = []
    test_start = min_train

    while test_start + test <= n:
        train_idx = np.arange(0, test_start, dtype=np.int64)
        test_idx = np.arange(test_start, test_start + test, dtype=np.int64)
        if train_idx.size == 0:
            raise ValueError(f"fold at test_start={test_start}: empty train window")
        if test_idx.size == 0:
            raise ValueError(f"fold at test_start={test_start}: empty test window")
        if train_idx.max() >= test_idx.min():
            raise ValueError(
                f"fold at test_start={test_start}: train/test overlap "
                f"(train max={train_idx.max()}, test min={test_idx.min()})"
            )
        folds.append((train_idx, test_idx))
        test_start += step

    if not folds:
        raise ValueError(
            f"no valid folds for n={n} (min_train={min_train}, test={test}, step={step})"
        )

    return folds
