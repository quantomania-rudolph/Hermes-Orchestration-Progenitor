"""NGINX log analyzer configuration with orchestrator smoke defaults."""

from __future__ import annotations

import os
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent

SMOKE = os.getenv("HERMES_LOG_ANALYZER_SMOKE", "1") == "1"

DEFAULT_LOG_PATH = _PKG_ROOT / "sample_data" / "access.log"
REPORT_DIR = _PKG_ROOT / "reports"
SUMMARY_JSON = REPORT_DIR / "summary.json"

TOP_N_PATHS = 5 if SMOKE else 20
MAX_LINES = 200 if SMOKE else 1_000_000
ERROR_STATUS_MIN = 400
