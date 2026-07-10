"""Data leakage audit pipeline configuration with orchestrator smoke defaults."""

from __future__ import annotations

import os
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent

# Smoke defaults keep CI and orchestrator dry-runs fast (override via HERMES_LEAKAGE_SMOKE=0).
SMOKE = os.getenv("HERMES_LEAKAGE_SMOKE", "1") == "1"

REPORT_DIR = _PKG_ROOT / "reports"
AUDIT_REPORT_JSON = REPORT_DIR / "leakage_audit.json"
AUDIT_REPORT_MD = REPORT_DIR / "leakage_audit.md"

TIMESTAMP_COLUMN = "timestamp"
VALUE_COLUMN = "value"
LABEL_COLUMN = "label"

TRAP_CLASS_CLEAN = "clean"
TRAP_CLASS_FUTURE_LABEL = "future_label"
TRAP_CLASS_SCALER_FIT = "scaler_fit"
TRAP_CLASS_INDEX_OVERLAP = "index_overlap"

DATASET_TAG_CLEAN = "clean_series"
DATASET_TAG_FUTURE_LABEL = "future_label_trap"
DATASET_TAG_SCALER = "scaler_trap"
DATASET_TAG_OVERLAP = "overlap_trap"

ALL_DATASET_TAGS: tuple[str, ...] = (
    DATASET_TAG_CLEAN,
    DATASET_TAG_FUTURE_LABEL,
    DATASET_TAG_SCALER,
    DATASET_TAG_OVERLAP,
)

N_BARS = 120 if SMOKE else 2_000
NUM_LAGS = 2 if SMOKE else 4
MIN_TRAIN_ROWS = 60 if SMOKE else 400
TEST_ROWS = 20 if SMOKE else 100
EMBARGO_BARS = 2 if SMOKE else 5
OVERLAP_FRACTION = 0.15

RANDOM_STATE = 42

# Minimum raw bars so post-lag dropna still satisfies train + embargo + test.
MIN_BARS = MIN_TRAIN_ROWS + EMBARGO_BARS + TEST_ROWS + NUM_LAGS + 3

FEATURE_COLUMNS: list[str] = [f"return_lag{i}" for i in range(1, NUM_LAGS + 1)]

__all__ = [
    "ALL_DATASET_TAGS",
    "AUDIT_REPORT_JSON",
    "AUDIT_REPORT_MD",
    "DATASET_TAG_CLEAN",
    "DATASET_TAG_FUTURE_LABEL",
    "DATASET_TAG_OVERLAP",
    "DATASET_TAG_SCALER",
    "EMBARGO_BARS",
    "FEATURE_COLUMNS",
    "LABEL_COLUMN",
    "MIN_BARS",
    "MIN_TRAIN_ROWS",
    "N_BARS",
    "NUM_LAGS",
    "OVERLAP_FRACTION",
    "RANDOM_STATE",
    "REPORT_DIR",
    "SMOKE",
    "TEST_ROWS",
    "TIMESTAMP_COLUMN",
    "TRAP_CLASS_CLEAN",
    "TRAP_CLASS_FUTURE_LABEL",
    "TRAP_CLASS_INDEX_OVERLAP",
    "TRAP_CLASS_SCALER_FIT",
    "VALUE_COLUMN",
]
