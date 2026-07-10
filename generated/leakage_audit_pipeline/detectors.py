"""Automated leakage detectors for quant research audit drills."""

from __future__ import annotations

import importlib.util
import math
from dataclasses import asdict, dataclass, field
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

TRAP_CLASS_FUTURE_LABEL = _cfg.TRAP_CLASS_FUTURE_LABEL
TRAP_CLASS_INDEX_OVERLAP = _cfg.TRAP_CLASS_INDEX_OVERLAP
TRAP_CLASS_SCALER_FIT = _cfg.TRAP_CLASS_SCALER_FIT
FEATURE_COLUMNS = _cfg.FEATURE_COLUMNS

# Correlation spike threshold for future-information leakage.
CORR_SPIKE_THRESHOLD = 0.90
# Contemporaneous corr must exceed lagged-label corr by this margin.
SHIFT_CORR_MARGIN = 0.15
# Fraction of rows that must match labels to flag exact future copy.
EXACT_MATCH_FRACTION = 0.95
# Scaler-fit-on-test signature: both splits look standard-normalized.
SCALER_MEAN_THRESHOLD = 0.20
SCALER_STD_TOLERANCE = 0.25
# Share of shared feature columns that must look normalized in both splits.
MIN_NORMALIZED_FRACTION = 0.5
# Cap serialized overlap indices to keep audit JSON bounded.
MAX_OVERLAP_INDEX_SAMPLE = 64

__all__ = [
    "CORR_SPIKE_THRESHOLD",
    "EXACT_MATCH_FRACTION",
    "LeakageFinding",
    "MAX_OVERLAP_INDEX_SAMPLE",
    "MIN_NORMALIZED_FRACTION",
    "SCALER_MEAN_THRESHOLD",
    "SCALER_STD_TOLERANCE",
    "SHIFT_CORR_MARGIN",
    "compute_feature_stats",
    "detect_future_shift",
    "detect_index_overlap",
    "detect_scaler_leakage",
    "findings_to_dicts",
]


@dataclass(frozen=True)
class LeakageFinding:
    """Structured leakage signal consumed by audit_runner and pytest traps."""

    detector: str
    trap_class: str
    severity: float
    message: str
    details: dict[str, Any] = field(default_factory=dict)


def findings_to_dicts(findings: list[LeakageFinding]) -> list[dict[str, Any]]:
    """Serialize findings for JSON audit reports."""
    return [asdict(f) for f in findings]


def _as_float_series(values: pd.Series | np.ndarray | list[float]) -> pd.Series:
    if isinstance(values, pd.Series):
        return values.astype(float)
    return pd.Series(values, dtype=float)


def _aligned_pairs(
    features: pd.DataFrame,
    labels: pd.Series | np.ndarray | list[float],
) -> tuple[pd.DataFrame, pd.Series]:
    if features.empty:
        return features, pd.Series(dtype=float)
    label_series = _as_float_series(labels)
    if len(label_series) != len(features):
        raise ValueError(
            f"features rows ({len(features)}) must match labels length ({len(label_series)})"
        )
    frame = features.copy()
    frame["_label"] = label_series.values
    frame = frame.dropna()
    if frame.empty:
        return pd.DataFrame(columns=features.columns), pd.Series(dtype=float)
    aligned_labels = frame.pop("_label")
    return frame, aligned_labels


def _pearson_corr(x: pd.Series, y: pd.Series) -> float:
    if len(x) < 2:
        return 0.0
    corr = x.corr(y)
    if corr is None or math.isnan(corr):
        return 0.0
    return float(corr)


def _exact_match_fraction(feature: pd.Series, labels: pd.Series) -> float:
    if len(feature) == 0:
        return 0.0
    delta = (feature.astype(float) - labels.astype(float)).abs()
    return float((delta <= 1e-10).mean())


def _shift_corr_spike(feature: pd.Series, labels: pd.Series) -> tuple[float, float, float]:
    """Return contemporaneous corr, lagged-label corr, and their signed gap."""
    if len(feature) < 3:
        return 0.0, 0.0, 0.0
    contemporaneous = _pearson_corr(feature, labels)
    past_labels = labels.shift(1)
    valid = past_labels.notna()
    if int(valid.sum()) < 2:
        return contemporaneous, 0.0, contemporaneous
    lagged = _pearson_corr(feature[valid], past_labels[valid])
    return contemporaneous, lagged, contemporaneous - lagged


def _as_index_array(idx: np.ndarray | list[int] | pd.Index) -> np.ndarray:
    return np.asarray(idx, dtype=np.int64)


def _validate_stats_bundle(stats: Any, name: str) -> None:
    if not isinstance(stats, dict):
        raise TypeError(f"{name} must be dict[str, dict[str, float]], got {type(stats).__name__}")
    for column, column_stats in stats.items():
        if not isinstance(column, str):
            raise TypeError(f"{name} keys must be str feature names, got {type(column).__name__}")
        if not isinstance(column_stats, dict):
            raise TypeError(
                f"{name}[{column!r}] must be dict[str, float], got {type(column_stats).__name__}"
            )


def compute_feature_stats(
    frame: pd.DataFrame,
    idx: np.ndarray | list[int] | pd.Index,
    *,
    columns: list[str] | None = None,
) -> dict[str, dict[str, float]]:
    """Compute per-column mean/std for a row subset (pass scaled features for scaler audit)."""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"frame must be DataFrame, got {type(frame).__name__}")
    row_idx = _as_index_array(idx)
    if row_idx.size == 0:
        return {}
    subset = frame.iloc[row_idx]
    feature_columns = columns if columns is not None else list(FEATURE_COLUMNS)
    stats: dict[str, dict[str, float]] = {}
    for column in feature_columns:
        if column not in subset.columns:
            continue
        series = subset[column].astype(float)
        stats[column] = {
            "mean": float(series.mean()),
            "std": float(series.std(ddof=0)),
        }
    return stats


def _is_normalized_split_stats(stats: dict[str, float]) -> bool:
    mean = float(stats.get("mean", float("nan")))
    std = float(stats.get("std", float("nan")))
    if math.isnan(mean) or math.isnan(std):
        return False
    return abs(mean) <= SCALER_MEAN_THRESHOLD and abs(std - 1.0) <= SCALER_STD_TOLERANCE


def detect_future_shift(
    features: pd.DataFrame,
    labels: pd.Series | np.ndarray | list[float],
) -> list[LeakageFinding]:
    """Flag features that spike in correlation with contemporaneous forward labels."""
    if not isinstance(features, pd.DataFrame):
        raise TypeError(f"features must be DataFrame, got {type(features).__name__}")

    aligned_features, aligned_labels = _aligned_pairs(features, labels)
    if aligned_features.empty:
        return []

    configured = [col for col in FEATURE_COLUMNS if col in aligned_features.columns]
    columns_to_check = configured or list(aligned_features.columns)

    findings: list[LeakageFinding] = []
    for column in columns_to_check:
        series = aligned_features[column].astype(float)
        correlation, lagged_correlation, shift_gap = _shift_corr_spike(series, aligned_labels)
        match_fraction = _exact_match_fraction(series, aligned_labels)
        abs_corr = abs(correlation)
        shift_spike = abs(shift_gap) >= SHIFT_CORR_MARGIN and abs_corr > abs(lagged_correlation)

        if (
            abs_corr < CORR_SPIKE_THRESHOLD
            and match_fraction < EXACT_MATCH_FRACTION
            and not shift_spike
        ):
            continue

        severity = max(abs_corr, match_fraction, min(1.0, abs(shift_gap)))
        reasons: list[str] = []
        if abs_corr >= CORR_SPIKE_THRESHOLD:
            reasons.append(f"correlation={correlation:.4f}")
        if shift_spike:
            reasons.append(
                f"shift_gap={shift_gap:.4f} (lagged_correlation={lagged_correlation:.4f})"
            )
        if match_fraction >= EXACT_MATCH_FRACTION:
            reasons.append(f"exact_match_fraction={match_fraction:.4f}")

        findings.append(
            LeakageFinding(
                detector="future_shift",
                trap_class=TRAP_CLASS_FUTURE_LABEL,
                severity=float(min(1.0, severity)),
                message=(
                    f"feature '{column}' shows future-information leakage "
                    f"({', '.join(reasons)})"
                ),
                details={
                    "feature": str(column),
                    "correlation": correlation,
                    "abs_correlation": abs_corr,
                    "lagged_correlation": lagged_correlation,
                    "shift_gap": shift_gap,
                    "exact_match_fraction": match_fraction,
                    "corr_threshold": CORR_SPIKE_THRESHOLD,
                    "shift_margin": SHIFT_CORR_MARGIN,
                    "match_threshold": EXACT_MATCH_FRACTION,
                    "n_rows": int(len(series)),
                },
            )
        )

    return findings


def detect_scaler_leakage(
    train_stats: dict[str, dict[str, float]],
    test_stats: dict[str, dict[str, float]],
) -> list[LeakageFinding]:
    """Flag scaler leakage when train and test splits both look globally normalized.

    Callers must pass stats computed on the post-transform feature matrix (e.g. via
    ``compute_feature_stats`` on scaled columns). Raw pre-scale marginals will not trigger.
    """
    _validate_stats_bundle(train_stats, "train_stats")
    _validate_stats_bundle(test_stats, "test_stats")
    if not train_stats or not test_stats:
        return []

    shared_columns = sorted(set(train_stats) & set(test_stats))
    if not shared_columns:
        return []

    normalized_columns: list[str] = []
    column_details: dict[str, dict[str, Any]] = {}

    for column in shared_columns:
        train_col = train_stats[column]
        test_col = test_stats[column]
        train_norm = _is_normalized_split_stats(train_col)
        test_norm = _is_normalized_split_stats(test_col)
        column_details[column] = {
            "train_mean": float(train_col.get("mean", float("nan"))),
            "train_std": float(train_col.get("std", float("nan"))),
            "test_mean": float(test_col.get("mean", float("nan"))),
            "test_std": float(test_col.get("std", float("nan"))),
            "train_normalized": train_norm,
            "test_normalized": test_norm,
        }
        if train_norm and test_norm:
            normalized_columns.append(column)

    if not normalized_columns:
        return []

    coverage = len(normalized_columns) / len(shared_columns)
    if coverage < MIN_NORMALIZED_FRACTION:
        return []

    severity = float(min(1.0, 0.5 + 0.5 * coverage))

    return [
        LeakageFinding(
            detector="scaler_leakage",
            trap_class=TRAP_CLASS_SCALER_FIT,
            severity=severity,
            message=(
                "train and test feature stats are both near zero-mean/unit-variance, "
                "consistent with scaler fit on combined data"
            ),
            details={
                "normalized_columns": normalized_columns,
                "normalized_fraction": coverage,
                "min_normalized_fraction": MIN_NORMALIZED_FRACTION,
                "mean_threshold": SCALER_MEAN_THRESHOLD,
                "std_tolerance": SCALER_STD_TOLERANCE,
                "columns": column_details,
            },
        )
    ]


def detect_index_overlap(
    train_idx: np.ndarray | list[int] | pd.Index,
    test_idx: np.ndarray | list[int] | pd.Index,
) -> list[LeakageFinding]:
    """Flag train/test index intersection (purged split violation)."""
    for name, idx in (("train_idx", train_idx), ("test_idx", test_idx)):
        if not isinstance(idx, (np.ndarray, list, pd.Index)):
            raise TypeError(f"{name} must be array-like, got {type(idx).__name__}")
    train = _as_index_array(train_idx)
    test = _as_index_array(test_idx)

    if train.size == 0 or test.size == 0:
        return []

    overlapping = np.intersect1d(train, test)
    if overlapping.size == 0:
        return []

    overlap_fraction = float(overlapping.size / test.size)
    severity = float(min(1.0, max(overlap_fraction, overlapping.size / max(train.size, 1))))
    overlap_list = [int(x) for x in overlapping.tolist()]
    sampled = overlap_list[:MAX_OVERLAP_INDEX_SAMPLE]

    return [
        LeakageFinding(
            detector="index_overlap",
            trap_class=TRAP_CLASS_INDEX_OVERLAP,
            severity=severity,
            message=(
                f"train/test index overlap detected ({overlapping.size} shared indices)"
            ),
            details={
                "overlap_count": int(overlapping.size),
                "overlap_fraction_of_test": overlap_fraction,
                "overlapping_indices": sampled,
                "overlapping_indices_truncated": len(overlap_list) > len(sampled),
                "train_size": int(train.size),
                "test_size": int(test.size),
            },
        )
    ]
