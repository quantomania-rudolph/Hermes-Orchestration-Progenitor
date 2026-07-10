"""Sequence tensors and per-fold feature scaling for the LSTM pipeline.

``build_sequences`` stacks past-bar feature windows aligned to each prediction
point (§6.2): for sequence ending at row ``i``, ``X`` uses feature rows
``[i - lookback + 1 .. i]`` and labels come from row ``i`` only — row ``i + 1``
is never included in ``X[i]``.

``FoldScaler`` fits z-score statistics on the train fold only (invariant L3).
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

import config
from signals import (
    DIRECTION_COL,
    FEATURE_COLS,
    LABEL_COL,
    MACD_WARMUP,
    ROLLING_WARMUP,
)

MIN_SEQUENCE_ROWS = config.LOOKBACK + MACD_WARMUP + ROLLING_WARMUP
_EPS = 1e-8

__all__ = [
    "MIN_SEQUENCE_ROWS",
    "FoldScaler",
    "build_sequences",
    "minimum_rows",
]


def minimum_rows(*, lookback: int | None = None) -> int:
    """Minimum feature-frame row count required for sequence construction."""
    lb = config.LOOKBACK if lookback is None else lookback
    return lb + MACD_WARMUP + ROLLING_WARMUP


class FoldScaler:
    """Per-feature z-score scaler fit on train-fold sequences only."""

    def __init__(self, eps: float = _EPS) -> None:
        self.eps = eps
        self.mean_: np.ndarray | None = None
        self.std_: np.ndarray | None = None
        self.feature_cols_: list[str] | None = None
        self.n_features_: int | None = None

    @property
    def fitted(self) -> bool:
        return self.mean_ is not None and self.std_ is not None

    def fit(
        self,
        X: np.ndarray,
        *,
        feature_cols: Sequence[str] | None = None,
    ) -> FoldScaler:
        """Compute mean/std over all train samples and timesteps per feature."""
        arr = _as_sequence_array(X)
        flat = arr.reshape(-1, arr.shape[-1])
        self.mean_ = flat.mean(axis=0)
        self.std_ = flat.std(axis=0)
        self.std_ = np.where(self.std_ < self.eps, 1.0, self.std_)
        self.n_features_ = arr.shape[-1]
        if feature_cols is not None:
            if len(feature_cols) != self.n_features_:
                raise ValueError(
                    f"feature_cols length {len(feature_cols)} != n_features {self.n_features_}"
                )
            self.feature_cols_ = list(feature_cols)
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        """Apply train-fold statistics to ``X`` (train or test)."""
        if not self.fitted:
            raise RuntimeError("FoldScaler.transform called before fit")
        arr = _as_sequence_array(X)
        if arr.shape[-1] != self.n_features_:
            raise ValueError(
                f"expected {self.n_features_} features, got {arr.shape[-1]}"
            )
        return (arr - self.mean_) / self.std_

    def fit_transform(
        self,
        X: np.ndarray,
        *,
        feature_cols: Sequence[str] | None = None,
    ) -> np.ndarray:
        return self.fit(X, feature_cols=feature_cols).transform(X)

    def state_dict(self) -> dict[str, Any]:
        """Serialize scaler for fold checkpoint persistence."""
        if not self.fitted:
            raise RuntimeError("FoldScaler.state_dict called before fit")
        return {
            "mean": self.mean_.tolist(),
            "std": self.std_.tolist(),
            "feature_cols": self.feature_cols_,
            "n_features": self.n_features_,
            "eps": self.eps,
        }

    def load_state_dict(self, state: dict[str, Any]) -> FoldScaler:
        """Restore scaler from a checkpoint dict."""
        self.mean_ = np.asarray(state["mean"], dtype=np.float64)
        self.std_ = np.asarray(state["std"], dtype=np.float64)
        self.feature_cols_ = state.get("feature_cols")
        self.n_features_ = int(state["n_features"])
        self.eps = float(state.get("eps", _EPS))
        return self


def build_sequences(
    feature_df: pd.DataFrame,
    *,
    lookback: int = config.LOOKBACK,
    feature_cols: Sequence[str] | None = None,
    label_col: str = LABEL_COL,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Build LSTM-ready tensors from a leakage-safe feature frame.

    Alignment (§6.2): sequence ``k`` ends at row ``i = k + lookback - 1``.
    ``X[k]`` contains feature rows ``[i - lookback + 1 .. i]``; ``y_reg[k]``,
    ``y_cls[k]``, and ``ts[k]`` come from row ``i``.

    Returns
    -------
    X
        Shape ``(N, lookback, F)`` — past bars only.
    y_reg
        Shape ``(N,)`` — ``next_return`` at the sequence end row.
    y_cls
        Shape ``(N,)`` — direction ``{-1, 0, 1}`` at the sequence end row.
    ts
        Shape ``(N,)`` — ``bar_end_utc`` at each prediction point.
    """
    lb = lookback
    cols = list(FEATURE_COLS if feature_cols is None else feature_cols)
    min_rows = minimum_rows(lookback=lb)

    if lb < 1:
        raise ValueError(f"lookback must be >= 1, got {lb}")

    if feature_df is None or feature_df.empty:
        raise ValueError("feature_df is empty")

    if len(feature_df) < min_rows:
        raise ValueError(
            f"need at least {min_rows} feature rows "
            f"(lookback={lb} + MACD={MACD_WARMUP} + rolling={ROLLING_WARMUP}); "
            f"got {len(feature_df)}"
        )

    missing = [
        c
        for c in ("bar_end_utc", label_col, DIRECTION_COL, *cols)
        if c not in feature_df.columns
    ]
    if missing:
        raise ValueError(f"feature_df missing columns: {missing}")

    work = feature_df.reset_index(drop=True)
    features = work.loc[:, cols].to_numpy(dtype=np.float64)
    if not np.isfinite(features).all():
        raise ValueError("feature_df contains non-finite values in feature columns")

    # Window k -> feature rows [k .. k+lookback-1]; label/ts at row k+lookback-1.
    # sliding_window_view on axis=0 yields (N, F, lookback); transpose to (N, lookback, F).
    windows = sliding_window_view(features, lb, axis=0)
    X = np.moveaxis(np.asarray(windows, dtype=np.float64), -1, 1).copy()
    if X.ndim != 3 or X.shape[1] != lb or X.shape[2] != len(cols):
        raise RuntimeError(
            f"expected X shape (N, {lb}, {len(cols)}), got {X.shape}"
        )

    end_idx = np.arange(lb - 1, len(work), dtype=int)
    y_reg = work.loc[end_idx, label_col].to_numpy(dtype=np.float64)
    y_cls = work.loc[end_idx, DIRECTION_COL].to_numpy(dtype=np.int64)
    ts = work.loc[end_idx, "bar_end_utc"].to_numpy()

    n = len(end_idx)
    if X.shape[0] != n:
        raise RuntimeError(
            f"sequence count mismatch: X has {X.shape[0]} windows, expected {n}"
        )

    if not np.isfinite(y_reg).all():
        raise ValueError("label column contains non-finite values")

    return X, y_reg, y_cls, ts


def _as_sequence_array(X: np.ndarray) -> np.ndarray:
    arr = np.asarray(X, dtype=np.float64)
    if arr.ndim == 2:
        arr = arr[:, np.newaxis, :]
    if arr.ndim != 3:
        raise ValueError(f"expected 2D or 3D array, got shape {arr.shape}")
    if not np.isfinite(arr).all():
        raise ValueError("input contains non-finite values")
    return arr
