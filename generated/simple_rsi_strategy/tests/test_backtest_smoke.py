"""Smoke tests for backtest_pnl offline hook."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_PKG = Path(__file__).resolve().parents[1]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

os.environ.setdefault("HERMES_RSI_SMOKE", "1")


def test_backtest_runs_offline():
    from backtest_pnl import verify

    assert verify()["ok"]
