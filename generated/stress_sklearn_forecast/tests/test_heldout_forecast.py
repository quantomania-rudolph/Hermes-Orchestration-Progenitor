"""Held-out forecast probes (DAEDALUS R23)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_PKG = Path(__file__).resolve().parents[1]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

from config import DEFAULT_CSV_PATH
from features import assert_no_leakage, build_features


def test_heldout_feature_index_monotonic():
    df = pd.read_csv(DEFAULT_CSV_PATH)
    feat = build_features(df)
    assert feat.index.is_monotonic_increasing
    assert_no_leakage(feat)
