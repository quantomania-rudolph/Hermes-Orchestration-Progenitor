"""Smoke tests for simple_rsi_strategy bar loader."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_PKG = Path(__file__).resolve().parents[1]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

os.environ.setdefault("HERMES_RSI_SMOKE", "1")

from data_loader import load_bars


def test_load_bars_sample_csv():
    df = load_bars("AAPL", "5min")
    assert len(df) >= 50
    assert "close" in df.columns
