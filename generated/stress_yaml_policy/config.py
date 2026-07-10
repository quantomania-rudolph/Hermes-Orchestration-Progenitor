"""YAML policy validator configuration with orchestrator smoke defaults."""

from __future__ import annotations

import os
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent

SMOKE = os.getenv("HERMES_POLICY_SMOKE", "1") == "1"

DEFAULT_POLICY_PATH = _PKG_ROOT / "sample_data" / "policy.yaml"
REPORT_PATH = _PKG_ROOT / "reports" / "validation.json"

MAX_RULES = 10 if SMOKE else 1000
