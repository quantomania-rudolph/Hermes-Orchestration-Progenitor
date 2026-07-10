"""CSV ETL quality pipeline configuration with orchestrator smoke defaults."""

from __future__ import annotations

import os
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent

SMOKE = os.getenv("HERMES_ETL_SMOKE", "1") == "1"

DEFAULT_CSV_PATH = _PKG_ROOT / "sample_data" / "transactions.csv"
REPORT_DIR = _PKG_ROOT / "reports"
QUALITY_REPORT_JSON = REPORT_DIR / "quality_report.json"
QUALITY_REPORT_MD = REPORT_DIR / "quality_report.md"

MAX_ROWS = 200 if SMOKE else 10_000
IQR_MULTIPLIER = 1.5
MAX_NULL_RATE = 0.02 if SMOKE else 0.01
MAX_DUPLICATE_IDS = 0
