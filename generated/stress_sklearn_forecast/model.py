"""Ridge regression fold training and out-of-sample prediction for walk-forward backtests."""

from __future__ import annotations

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.utils.validation import check_is_fitted

try:
    from config import RIDGE_ALPHA, RANDOM_STATE
except ImportError:  # pragma: no cover - package import when run as module
    from .config import RIDGE_ALPHA, RANDOM_STATE

__all__ = ["train_fold", "predict_oos"]


def _as_2d(X: object) -> np.ndarray:
    """Coerce feature matrix to a finite float ndarray with shape (n_samples, n_features)."""
    arr = np.asarray(X, dtype=float)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    elif arr.ndim != 2:
        raise ValueError(f"X must be 1D or 2D, got shape {arr.shape}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("X contains non-finite values")
    return arr


def _as_1d(y: object) -> np.ndarray:
    """Coerce target vector to a finite float ndarray with shape (n_samples,)."""
    arr = np.asarray(y, dtype=float)
    if arr.ndim == 2 and arr.shape[1] == 1:
        arr = arr[:, 0]
    elif arr.ndim != 1:
        raise ValueError(f"y must be 1D or a single-column vector, got shape {arr.shape}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("y contains non-finite values")
    return arr


def train_fold(
    X_train: object,
    y_train: object,
    *,
    alpha: float = RIDGE_ALPHA,
    random_state: int = RANDOM_STATE,
) -> Ridge:
    """Fit a Ridge regressor on one expanding-window training fold."""
    X = _as_2d(X_train)
    y = _as_1d(y_train)

    if X.shape[0] == 0:
        raise ValueError("X_train is empty")
    if y.shape[0] == 0:
        raise ValueError("y_train is empty")
    if X.shape[0] != y.shape[0]:
        raise ValueError(
            f"X_train and y_train row mismatch: {X.shape[0]} vs {y.shape[0]}"
        )
    if X.shape[1] == 0:
        raise ValueError("X_train has zero features")
    if alpha < 0:
        raise ValueError(f"alpha must be >= 0, got {alpha}")

    model = Ridge(alpha=alpha, random_state=random_state)
    model.fit(X, y)
    return model


def predict_oos(model: Ridge, X_test: object) -> np.ndarray:
    """Predict out-of-sample targets for a fitted Ridge model."""
    if model is None:
        raise ValueError("model is None")
    check_is_fitted(model)

    X = _as_2d(X_test)
    if X.shape[0] == 0:
        raise ValueError("X_test is empty")
    if X.shape[1] == 0:
        raise ValueError("X_test has zero features")

    preds = model.predict(X)
    out = np.asarray(preds, dtype=float).ravel()
    if out.shape[0] != X.shape[0]:
        raise ValueError(
            f"model.predict returned {out.shape[0]} rows for {X.shape[0]} test rows"
        )
    if not np.all(np.isfinite(out)):
        raise ValueError("model produced non-finite OOS predictions")
    return out
