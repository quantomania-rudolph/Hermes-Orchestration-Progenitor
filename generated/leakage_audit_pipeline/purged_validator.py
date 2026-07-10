"""Purged train/test split validation with embargo and detector integration."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_PKG_ROOT = Path(__file__).resolve().parent
_CONFIG_MODULE = "leakage_audit_pipeline.config"
_DETECTORS_MODULE = "leakage_audit_pipeline.detectors"


def _ensure_parent_modules(qualified_name: str) -> None:
    """Stub parent packages so dotted spec names resolve under T17 fuzz imports."""
    parts = qualified_name.split(".")
    for i in range(1, len(parts)):
        parent_name = ".".join(parts[:i])
        if parent_name in sys.modules:
            continue
        parent = types.ModuleType(parent_name)
        parent.__path__ = [str(_PKG_ROOT)]
        sys.modules[parent_name] = parent


def _load_sibling_module(qualified_name: str, filename: str):
    """Load sibling module with sys.modules registration (fuzz-safe)."""
    cached = sys.modules.get(qualified_name)
    if cached is not None:
        return cached

    module_path = _PKG_ROOT / filename
    if not module_path.is_file():
        raise ImportError(f"cannot find {filename} at {module_path}")

    _ensure_parent_modules(qualified_name)
    spec = importlib.util.spec_from_file_location(qualified_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {filename} from {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified_name] = module
    spec.loader.exec_module(module)
    return module


def _load_config():
    """Load sibling config.py without package-relative imports (T17 fuzz loads as fuzz_mod)."""
    return _load_sibling_module(_CONFIG_MODULE, "config.py")


def _load_detectors():
    """Load sibling detectors.py without package-relative imports."""
    _load_config()
    return _load_sibling_module(_DETECTORS_MODULE, "detectors.py")


_cfg = _load_config()
_det = _load_detectors()

EMBARGO_BARS = _cfg.EMBARGO_BARS
TRAP_CLASS_INDEX_OVERLAP = _cfg.TRAP_CLASS_INDEX_OVERLAP

LeakageFinding = _det.LeakageFinding
detect_index_overlap = _det.detect_index_overlap

__all__ = [
    "EMBARGO_BARS",
    "assert_purge_valid",
    "detect_purge_violations",
]


def _as_index_array(idx: np.ndarray | list[int] | pd.Index) -> np.ndarray:
    return np.asarray(idx, dtype=np.int64)


def _as_timestamp_series(timestamps: np.ndarray | pd.Series | list[Any]) -> pd.Series:
    if isinstance(timestamps, pd.Series):
        return pd.to_datetime(timestamps)
    return pd.to_datetime(np.asarray(timestamps))


def _ts_at(timestamps: pd.Series, idx: int) -> pd.Timestamp:
    return pd.Timestamp(timestamps.iloc[idx])


def _index_gap_bars(train_max: int, test_min: int) -> int:
    """Bars strictly between the last train row and first test row."""
    return int(test_min - train_max - 1)


def _is_strictly_chronological(indices: np.ndarray, timestamps: pd.Series) -> bool:
    if indices.size < 2:
        return True
    ordered = np.all(indices[:-1] < indices[1:])
    if not ordered:
        return False
    ts_values = timestamps.iloc[indices.tolist()]
    return bool(ts_values.is_monotonic_increasing)


def _split_in_bounds(idx: np.ndarray, n_timestamps: int) -> bool:
    return int(idx.min()) >= 0 and int(idx.max()) < n_timestamps


def detect_purge_violations(
    timestamps: np.ndarray | pd.Series | list[Any],
    train_idx: np.ndarray | list[int] | pd.Index,
    test_idx: np.ndarray | list[int] | pd.Index,
    *,
    embargo_bars: int = EMBARGO_BARS,
) -> list[LeakageFinding]:
    """Return structured purge violations; delegates overlap to ``detect_index_overlap``."""
    if isinstance(embargo_bars, bool) or not isinstance(embargo_bars, int):
        raise TypeError(f"embargo_bars must be int, got {type(embargo_bars).__name__}")
    if embargo_bars < 0:
        raise ValueError(f"embargo_bars must be >= 0, got {embargo_bars}")

    ts = _as_timestamp_series(timestamps)
    train = _as_index_array(train_idx)
    test = _as_index_array(test_idx)

    findings: list[LeakageFinding] = list(detect_index_overlap(train, test))

    if len(ts) == 0:
        findings.append(
            LeakageFinding(
                detector="purged_validator",
                trap_class=TRAP_CLASS_INDEX_OVERLAP,
                severity=1.0,
                message="timestamps are empty",
                details={"timestamp_len": 0, "embargo_bars": embargo_bars},
            )
        )
        return findings

    if train.size == 0 or test.size == 0:
        empty_split = "train" if train.size == 0 else "test"
        findings.append(
            LeakageFinding(
                detector="purged_validator",
                trap_class=TRAP_CLASS_INDEX_OVERLAP,
                severity=1.0,
                message=f"{empty_split} split is empty",
                details={
                    "train_size": int(train.size),
                    "test_size": int(test.size),
                    "embargo_bars": embargo_bars,
                },
            )
        )
        return findings

    bounds_ok = True
    for name, idx in (("train", train), ("test", test)):
        if not _split_in_bounds(idx, len(ts)):
            bounds_ok = False
            findings.append(
                LeakageFinding(
                    detector="purged_validator",
                    trap_class=TRAP_CLASS_INDEX_OVERLAP,
                    severity=1.0,
                    message=f"{name} indices fall outside timestamp range",
                    details={
                        "split": name,
                        "index_min": int(idx.min()),
                        "index_max": int(idx.max()),
                        "timestamp_len": int(len(ts)),
                    },
                )
            )
    if not bounds_ok:
        return findings

    train_max = int(train.max())
    test_min = int(test.min())
    test_max = int(test.max())

    if train_max >= test_min:
        findings.append(
            LeakageFinding(
                detector="purged_validator",
                trap_class=TRAP_CLASS_INDEX_OVERLAP,
                severity=1.0,
                message=(
                    f"train max index {train_max} must be strictly before "
                    f"test min index {test_min}"
                ),
                details={
                    "train_max": train_max,
                    "test_min": test_min,
                    "embargo_bars": embargo_bars,
                },
            )
        )

    if not _is_strictly_chronological(train, ts):
        findings.append(
            LeakageFinding(
                detector="purged_validator",
                trap_class=TRAP_CLASS_INDEX_OVERLAP,
                severity=0.85,
                message="train indices or timestamps are not chronologically ordered",
                details={"split": "train", "train_size": int(train.size)},
            )
        )

    if not _is_strictly_chronological(test, ts):
        findings.append(
            LeakageFinding(
                detector="purged_validator",
                trap_class=TRAP_CLASS_INDEX_OVERLAP,
                severity=0.85,
                message="test indices or timestamps are not chronologically ordered",
                details={"split": "test", "test_size": int(test.size)},
            )
        )

    train_max_ts = _ts_at(ts, train_max)
    test_min_ts = _ts_at(ts, test_min)
    if train_max_ts >= test_min_ts:
        findings.append(
            LeakageFinding(
                detector="purged_validator",
                trap_class=TRAP_CLASS_INDEX_OVERLAP,
                severity=1.0,
                message="train max timestamp must be strictly before test min timestamp",
                details={
                    "train_max_ts": str(train_max_ts),
                    "test_min_ts": str(test_min_ts),
                },
            )
        )

    purge_gap = _index_gap_bars(train_max, test_min)
    if purge_gap < embargo_bars:
        severity = float(min(1.0, 0.5 + 0.5 * (1.0 - purge_gap / max(embargo_bars, 1))))
        findings.append(
            LeakageFinding(
                detector="purged_validator",
                trap_class=TRAP_CLASS_INDEX_OVERLAP,
                severity=severity,
                message=(
                    f"embargo gap {purge_gap} bars is less than required {embargo_bars}"
                ),
                details={
                    "purge_gap_bars": purge_gap,
                    "required_embargo_bars": embargo_bars,
                    "train_max": train_max,
                    "test_min": test_min,
                    "test_max": test_max,
                },
            )
        )

    return findings


def assert_purge_valid(
    timestamps: np.ndarray | pd.Series | list[Any],
    train_idx: np.ndarray | list[int] | pd.Index,
    test_idx: np.ndarray | list[int] | pd.Index,
    *,
    embargo_bars: int = EMBARGO_BARS,
) -> None:
    """Hard leakage gate: embargo bars, chronological ordering, no index intersection."""
    findings = detect_purge_violations(
        timestamps,
        train_idx,
        test_idx,
        embargo_bars=embargo_bars,
    )
    if not findings:
        return

    messages = [finding.message for finding in findings]
    raise AssertionError("; ".join(messages))
