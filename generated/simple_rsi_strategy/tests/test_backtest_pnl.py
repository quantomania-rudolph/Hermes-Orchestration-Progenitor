"""Tests for backtest_pnl verification gate."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backtest_pnl import run_backtest, verify


def test_run_backtest_finite():
    m = run_backtest()
    assert m["finite_pnl"]
    assert m["trade_count"] > 0


def test_verify_passes():
    assert verify() is True
