"""OOS walk-forward Ridge backtest with MAE/RMSE metrics for sklearn forecast pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_PKG_ROOT = Path(__file__).resolve().parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

try:
    from config import (
        DEFAULT_CSV_PATH,
        MAX_ROWS,
        METRICS_JSON,
        MIN_TRAIN_ROWS,
        STEP_ROWS,
        TEST_ROWS,
    )
except ImportError:  # pragma: no cover - package import when run as module
    from .config import (
        DEFAULT_CSV_PATH,
        MAX_ROWS,
        METRICS_JSON,
        MIN_TRAIN_ROWS,
        STEP_ROWS,
        TEST_ROWS,
    )

try:
    from features import FEATURE_COLS, LABEL_COLUMN, build_features
except ImportError:  # pragma: no cover - package import when run as module
    from .features import FEATURE_COLS, LABEL_COLUMN, build_features

try:
    from model import predict_oos, train_fold
except ImportError:  # pragma: no cover - package import when run as module
    from .model import predict_oos, train_fold

try:
    from splits import expanding_window_splits
except ImportError:  # pragma: no cover - package import when run as module
    from .splits import expanding_window_splits

__all__ = ["run_backtest", "write_metrics", "main"]

_METRICS_KEYS = ("mae", "rmse", "oos_rows")


def _load_series(csv_path: Path) -> pd.DataFrame:
    """Load and truncate the input CSV fixture to ``MAX_ROWS``."""
    df = pd.read_csv(csv_path)
    if MAX_ROWS is not None and len(df) > MAX_ROWS:
        df = df.iloc[:MAX_ROWS].copy()
    return df


def _oos_errors(y_true: np.ndarray, y_pred: np.ndarray) -> tuple[float, float]:
    """Compute MAE and RMSE on concatenated out-of-sample predictions."""
    if y_true.shape[0] == 0:
        raise ValueError("no OOS rows to score")
    if y_true.shape != y_pred.shape:
        raise ValueError(
            f"OOS shape mismatch: y_true {y_true.shape} vs y_pred {y_pred.shape}"
        )
    err = y_pred - y_true
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err**2)))
    if not np.isfinite(mae) or not np.isfinite(rmse):
        raise ValueError("OOS metrics are non-finite")
    return mae, rmse


def _validate_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    """Reject metrics payloads that do not match the reports/metrics.json contract."""
    missing = [key for key in _METRICS_KEYS if key not in metrics]
    if missing:
        raise ValueError(f"metrics missing required keys: {missing}")

    extra = [key for key in metrics if key not in _METRICS_KEYS]
    if extra:
        raise ValueError(f"metrics has unexpected keys: {extra}")

    mae = metrics["mae"]
    rmse = metrics["rmse"]
    oos_rows = metrics["oos_rows"]

    if not isinstance(mae, (int, float)) or not np.isfinite(float(mae)):
        raise ValueError(f"mae must be a finite number, got {mae!r}")
    if not isinstance(rmse, (int, float)) or not np.isfinite(float(rmse)):
        raise ValueError(f"rmse must be a finite number, got {rmse!r}")
    if isinstance(oos_rows, bool) or not isinstance(oos_rows, int) or oos_rows < 1:
        raise ValueError(f"oos_rows must be a positive int, got {oos_rows!r}")

    return {
        "mae": float(mae),
        "rmse": float(rmse),
        "oos_rows": oos_rows,
    }


def run_backtest(
    *,
    csv_path: str | Path | None = None,
    report_path: Path | str | None = None,
    write: bool = True,
) -> dict[str, Any]:
    """
    Run expanding-window walk-forward Ridge regression and score OOS only.

    Writes ``reports/metrics.json`` with ``mae``, ``rmse``, and ``oos_rows``.
    """
    if STEP_ROWS < TEST_ROWS:
        raise ValueError(
            f"STEP_ROWS must be >= TEST_ROWS to avoid overlapping OOS windows "
            f"(STEP_ROWS={STEP_ROWS}, TEST_ROWS={TEST_ROWS})"
        )

    path = Path(csv_path) if csv_path is not None else DEFAULT_CSV_PATH
    raw = _load_series(path)
    feature_df = build_features(raw)

    X = feature_df[FEATURE_COLS].to_numpy(dtype=float)
    y = feature_df[LABEL_COLUMN].to_numpy(dtype=float)
    folds = expanding_window_splits(
        len(feature_df),
        min_train=MIN_TRAIN_ROWS,
        test=TEST_ROWS,
        step=STEP_ROWS,
    )

    oos_true: list[np.ndarray] = []
    oos_pred: list[np.ndarray] = []

    for train_idx, test_idx in folds:
        model = train_fold(X[train_idx], y[train_idx])
        preds = predict_oos(model, X[test_idx])
        oos_true.append(y[test_idx])
        oos_pred.append(preds)

    y_oos = np.concatenate(oos_true)
    pred_oos = np.concatenate(oos_pred)
    mae, rmse = _oos_errors(y_oos, pred_oos)

    metrics = _validate_metrics(
        {
            "mae": mae,
            "rmse": rmse,
            "oos_rows": int(y_oos.shape[0]),
        }
    )

    if write:
        write_metrics(metrics, report_path=report_path)

    return metrics


def write_metrics(
    metrics: dict[str, Any],
    *,
    report_path: Path | str | None = None,
) -> Path:
    """Persist backtest metrics to ``reports/metrics.json``."""
    payload = _validate_metrics(metrics)
    out = Path(report_path) if report_path is not None else METRICS_JSON
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI entry: run OOS walk-forward backtest and write metrics JSON."""
    parser = argparse.ArgumentParser(
        description="Run sklearn walk-forward forecast backtest (OOS only)."
    )
    parser.add_argument(
        "csv_path",
        nargs="?",
        default=str(DEFAULT_CSV_PATH),
        help="Path to series CSV fixture (default: sample_data/series.csv)",
    )
    parser.add_argument(
        "--report-path",
        default=None,
        help=f"Metrics JSON output path (default: {METRICS_JSON})",
    )
    args = parser.parse_args(argv)
    run_backtest(csv_path=args.csv_path, report_path=args.report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
