"""Smoke configuration for simple_rsi_strategy DAEDALUS campaigns."""

from __future__ import annotations

import os

SMOKE = os.getenv("HERMES_RSI_SMOKE", "1") == "1"
LIMIT_BARS = 500 if SMOKE else 50_000
