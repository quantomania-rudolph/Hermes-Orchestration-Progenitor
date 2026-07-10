"""Synthetic quant research datasets with planted leakage traps for audit drills."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_PKG_ROOT = Path(__file__).resolve().parent


def _load_config():
    """Load sibling config.py without package-relative imports (T17 fuzz loads as fuzz_mod)."""
    config_path = _PKG_ROOT / "config.py"
    spec = importlib.util.spec_from_file_location(
        "leakage_audit_pipeline.config",
        config_path,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load config from {config_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_cfg = _load_config()

DATASET_TAG_CLEAN = _cfg.DATASET_TAG_CLEAN
DATASET_TAG_FUTURE_LABEL = _cfg.DATASET_TAG_FUTURE_LABEL
DATASET_TAG_OVERLAP = _cfg.DATASET_TAG_OVERLAP
DATASET_TAG_SCALER = _cfg.DATASET_TAG_SCALER
EMBARGO_BARS = _cfg.EMBARGO_BARS
FEATURE_COLUMNS = _cfg.FEATURE_COLUMNS
LABEL_COLUMN = _cfg.LABEL_COLUMN
MIN_BARS = _cfg.MIN_BARS
MIN_TRAIN_ROWS = _cfg.MIN_TRAIN_ROWS
N_BARS = _cfg.N_BARS
NUM_LAGS = _cfg.NUM_LAGS
OVERLAP_FRACTION = _cfg.OVERLAP_FRACTION
RANDOM_STATE = _cfg.RANDOM_STATE
SMOKE = _cfg.SMOKE
TEST_ROWS = _cfg.TEST_ROWS
TIMESTAMP_COLUMN = _cfg.TIMESTAMP_COLUMN
TRAP_CLASS_CLEAN = _cfg.TRAP_CLASS_CLEAN
TRAP_CLASS_FUTURE_LABEL = _cfg.TRAP_CLASS_FUTURE_LABEL
TRAP_CLASS_INDEX_OVERLAP = _cfg.TRAP_CLASS_INDEX_OVERLAP
TRAP_CLASS_SCALER_FIT = _cfg.TRAP_CLASS_SCALER_FIT
VALUE_COLUMN = _cfg.VALUE_COLUMN

__all__ = [
    "SyntheticDataset",
    "future_label_trap",
    "generate_clean_series",
    "overlap_trap",
    "scaler_trap",
]


@dataclass(frozen=True)
class SyntheticDataset:
    """Pandas frame plus metadata tags consumed by leakage detectors."""

    df: pd.DataFrame
    metadata: dict[str, Any]


def _rng(seed: int | None = None) -> np.random.Generator:
    return np.random.default_rng(RANDOM_STATE if seed is None else seed)


def _ensure_n_bars(n_bars: int) -> None:
    if isinstance(n_bars, bool) or not isinstance(n_bars, int):
        raise TypeError(f"n_bars must be int, got {type(n_bars).__name__}")
    if n_bars < MIN_BARS:
        raise ValueError(
            f"n_bars must be >= {MIN_BARS} for train/test split; got {n_bars}"
        )


def _base_price_series(n_bars: int, *, seed: int | None = None) -> pd.Series:
    """Geometric random-walk prices for reproducible synthetic bars."""
    gen = _rng(seed)
    log_returns = gen.normal(loc=0.0002, scale=0.01, size=n_bars)
    prices = 100.0 * np.exp(np.cumsum(log_returns))
    timestamps = pd.date_range("2020-01-02 09:30:00", periods=n_bars, freq="5min")
    return pd.Series(prices, index=timestamps, name=VALUE_COLUMN)


def _bar_returns(values: pd.Series) -> pd.Series:
    return values.astype(float).pct_change()


def _clean_features(values: pd.Series) -> pd.DataFrame:
    """Lag returns shifted by one bar (no contemporaneous leakage)."""
    bar_return = _bar_returns(values)
    features: dict[str, pd.Series] = {}
    for lag in range(1, NUM_LAGS + 1):
        col = f"return_lag{lag}"
        if lag == 1:
            features[col] = bar_return.shift(1)
        else:
            features[col] = values.pct_change(lag).shift(1)
    return pd.DataFrame(features)


def _forward_labels(values: pd.Series) -> pd.Series:
    return _bar_returns(values).shift(-1).rename(LABEL_COLUMN)


def _assemble_frame(
    values: pd.Series,
    features: pd.DataFrame,
    labels: pd.Series,
) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            TIMESTAMP_COLUMN: values.index,
            VALUE_COLUMN: values.values,
            LABEL_COLUMN: labels.values,
        }
    )
    for col in features.columns:
        frame[col] = features[col].values
    return frame.dropna().reset_index(drop=True)


def _validate_frame_rows(frame: pd.DataFrame) -> None:
    required = MIN_TRAIN_ROWS + EMBARGO_BARS + TEST_ROWS
    if len(frame) < required:
        raise ValueError(
            f"assembled frame needs >= {required} rows after lag dropna; got {len(frame)}"
        )


def _chronological_split(
    n_rows: int,
    *,
    min_train: int = MIN_TRAIN_ROWS,
    test: int = TEST_ROWS,
    embargo: int = EMBARGO_BARS,
) -> tuple[np.ndarray, np.ndarray]:
    required = min_train + embargo + test
    if n_rows < required:
        raise ValueError(
            f"need at least {required} rows for train/embargo/test split; got {n_rows}"
        )
    test_start = n_rows - test
    train_end = test_start - embargo
    if train_end < min_train:
        raise ValueError(
            f"need at least {min_train} train rows after embargo; got {train_end}"
        )
    train_idx = np.arange(0, train_end, dtype=np.int64)
    test_idx = np.arange(test_start, n_rows, dtype=np.int64)
    return train_idx, test_idx


def _idx_as_list(idx: np.ndarray) -> list[int]:
    return [int(x) for x in np.asarray(idx, dtype=np.int64).tolist()]


def _feature_stats(frame: pd.DataFrame, idx: np.ndarray) -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = {}
    subset = frame.iloc[idx]
    for col in FEATURE_COLUMNS:
        series = subset[col].astype(float)
        stats[col] = {
            "mean": float(series.mean()),
            "std": float(series.std(ddof=0)),
        }
    return stats


def _metadata_base(
    *,
    dataset_tag: str,
    trap_class: str,
    has_leakage: bool,
    train_idx: np.ndarray,
    test_idx: np.ndarray,
    frame: pd.DataFrame,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "dataset_tag": dataset_tag,
        "trap_class": trap_class,
        "tags": [dataset_tag, trap_class],
        "has_leakage": has_leakage,
        "smoke_mode": SMOKE,
        "n_rows": len(frame),
        "feature_columns": list(FEATURE_COLUMNS),
        "label_column": LABEL_COLUMN,
        "timestamp_column": TIMESTAMP_COLUMN,
        "value_column": VALUE_COLUMN,
        "train_idx": _idx_as_list(train_idx),
        "test_idx": _idx_as_list(test_idx),
        "embargo_bars": EMBARGO_BARS,
        "train_stats": _feature_stats(frame, train_idx),
        "test_stats": _feature_stats(frame, test_idx),
    }
    if extra:
        meta.update(extra)
    return meta


def generate_clean_series(
    n_bars: int = N_BARS,
    *,
    seed: int | None = None,
) -> SyntheticDataset:
    """Leakage-free synthetic series with proper lag features and forward labels."""
    _ensure_n_bars(n_bars)
    values = _base_price_series(n_bars, seed=seed)
    features = _clean_features(values)
    labels = _forward_labels(values)
    frame = _assemble_frame(values, features, labels)
    _validate_frame_rows(frame)
    train_idx, test_idx = _chronological_split(len(frame))

    metadata = _metadata_base(
        dataset_tag=DATASET_TAG_CLEAN,
        trap_class=TRAP_CLASS_CLEAN,
        has_leakage=False,
        train_idx=train_idx,
        test_idx=test_idx,
        frame=frame,
    )
    return SyntheticDataset(df=frame, metadata=metadata)


def future_label_trap(
    n_bars: int = N_BARS,
    *,
    seed: int | None = None,
) -> SyntheticDataset:
    """Plant future-information leakage via a feature that copies the forward label."""
    _ensure_n_bars(n_bars)
    values = _base_price_series(n_bars, seed=seed)
    features = _clean_features(values)
    bar_return = _bar_returns(values)

    # Deliberate trap: return_lag1 equals the forward return (same as label).
    leaked_col = FEATURE_COLUMNS[0]
    features[leaked_col] = bar_return.shift(-1)

    labels = _forward_labels(values)
    frame = _assemble_frame(values, features, labels)
    _validate_frame_rows(frame)
    train_idx, test_idx = _chronological_split(len(frame))

    metadata = _metadata_base(
        dataset_tag=DATASET_TAG_FUTURE_LABEL,
        trap_class=TRAP_CLASS_FUTURE_LABEL,
        has_leakage=True,
        train_idx=train_idx,
        test_idx=test_idx,
        frame=frame,
        extra={
            "leaked_feature": leaked_col,
            "leak_mechanism": "future_return_in_feature",
        },
    )
    return SyntheticDataset(df=frame, metadata=metadata)


def scaler_trap(
    n_bars: int = N_BARS,
    *,
    seed: int | None = None,
) -> SyntheticDataset:
    """Plant scaler leakage by fitting normalization stats on train+test combined."""
    _ensure_n_bars(n_bars)
    values = _base_price_series(n_bars, seed=seed)
    features = _clean_features(values)
    labels = _forward_labels(values)
    frame = _assemble_frame(values, features, labels)
    _validate_frame_rows(frame)
    train_idx, test_idx = _chronological_split(len(frame))

    train_stats = _feature_stats(frame, train_idx)
    test_stats = _feature_stats(frame, test_idx)
    all_idx = np.arange(len(frame), dtype=np.int64)
    leaked_stats = _feature_stats(frame, all_idx)

    scaled = frame.copy()
    for col in FEATURE_COLUMNS:
        mean = leaked_stats[col]["mean"]
        std = leaked_stats[col]["std"] or 1.0
        scaled[col] = (scaled[col].astype(float) - mean) / std

    metadata = _metadata_base(
        dataset_tag=DATASET_TAG_SCALER,
        trap_class=TRAP_CLASS_SCALER_FIT,
        has_leakage=True,
        train_idx=train_idx,
        test_idx=test_idx,
        frame=scaled,
        extra={
            "leak_mechanism": "scaler_fit_on_train_plus_test",
            "features_scaled": True,
            "leaked_stats": leaked_stats,
            "scaled_feature_columns": list(FEATURE_COLUMNS),
        },
    )
    # Expose unscaled split stats for detect_scaler_leakage(train_stats, test_stats).
    metadata["train_stats"] = train_stats
    metadata["test_stats"] = test_stats
    return SyntheticDataset(df=scaled, metadata=metadata)


def overlap_trap(
    n_bars: int = N_BARS,
    *,
    seed: int | None = None,
    overlap_fraction: float = OVERLAP_FRACTION,
) -> SyntheticDataset:
    """Plant train/test index overlap by randomly reusing train rows in the test window."""
    _ensure_n_bars(n_bars)
    if not isinstance(overlap_fraction, (int, float)) or isinstance(overlap_fraction, bool):
        raise TypeError(
            f"overlap_fraction must be numeric, got {type(overlap_fraction).__name__}"
        )
    if not 0.0 < float(overlap_fraction) < 1.0:
        raise ValueError("overlap_fraction must be between 0 and 1 exclusive")

    gen = _rng(seed)
    values = _base_price_series(n_bars, seed=seed)
    features = _clean_features(values)
    labels = _forward_labels(values)
    frame = _assemble_frame(values, features, labels)
    _validate_frame_rows(frame)

    clean_train_idx, clean_test_idx = _chronological_split(len(frame))
    overlap_n = max(1, int(len(clean_test_idx) * overlap_fraction))
    overlap_idx = gen.choice(clean_train_idx, size=overlap_n, replace=False).astype(
        np.int64
    )
    test_idx = np.unique(np.concatenate([clean_test_idx, overlap_idx])).astype(np.int64)
    test_idx.sort()
    train_idx = clean_train_idx

    overlapping = np.intersect1d(train_idx, test_idx)

    metadata = _metadata_base(
        dataset_tag=DATASET_TAG_OVERLAP,
        trap_class=TRAP_CLASS_INDEX_OVERLAP,
        has_leakage=True,
        train_idx=train_idx,
        test_idx=test_idx,
        frame=frame,
        extra={
            "leak_mechanism": "train_test_index_overlap",
            "overlap_count": int(overlapping.size),
            "overlapping_indices": _idx_as_list(overlapping),
            "clean_test_idx": _idx_as_list(clean_test_idx),
        },
    )
    return SyntheticDataset(df=frame, metadata=metadata)
