"""Walk-forward sklearn forecast pipeline configuration with orchestrator smoke defaults."""

from __future__ import annotations

import os
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent

SMOKE = os.getenv("HERMES_FORECAST_SMOKE", "1") == "1"

DEFAULT_CSV_PATH = _PKG_ROOT / "sample_data" / "series.csv"
REPORT_DIR = _PKG_ROOT / "reports"
METRICS_JSON = REPORT_DIR / "metrics.json"

DATE_COLUMN = "date"
VALUE_COLUMN = "value"
LABEL_COLUMN = "next_return"

MAX_ROWS = 200 if SMOKE else 10_000

MIN_TRAIN_ROWS = 60
TEST_ROWS = 20
STEP_ROWS = 20

NUM_LAGS = 3 if SMOKE else 5
RIDGE_ALPHA = 1.0
RANDOM_STATE = 42
