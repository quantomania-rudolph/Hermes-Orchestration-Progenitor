"""Smoke tests for pairs_regime_ukf_trader universe bar loader."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

_PKG = Path(__file__).resolve().parents[1]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

os.environ.setdefault("HERMES_RESEARCH_SMOKE", "1")

from config import LIMIT_BARS, UNIVERSE
from data_loader import load_universe_bars


def test_load_universe_bars_sample_csv():
    df = load_universe_bars()
    assert len(df) >= 50
    assert df.columns.nlevels == 2
    assert df.index.name == "ts_utc" or isinstance(df.index, pd.DatetimeIndex)
    symbols = df.columns.get_level_values(0).unique().tolist()
    assert len(symbols) == len(UNIVERSE)
    for sym in UNIVERSE:
        assert sym in symbols
    fields = df.columns.get_level_values(1).unique().tolist()
    assert "close" in fields
    assert len(df) <= LIMIT_BARS
    closes = df.xs("close", axis=1, level=1)
    assert not closes.isna().any().any()
