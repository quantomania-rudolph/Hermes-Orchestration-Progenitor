"""FastAPI todo REST API configuration with orchestrator smoke defaults."""

from __future__ import annotations

import os
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent

SMOKE = os.getenv("HERMES_TODO_SMOKE", "1") == "1"

SQLITE_PATH = _PKG_ROOT / "data" / "todos.db"
MAX_ITEMS = 20 if SMOKE else 1000
API_KEY = os.getenv("API_KEY") or ("dev-smoke-key" if SMOKE else "")
