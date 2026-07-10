"""Held-out generalization probes (DAEDALUS R23). Matched by pytest -k heldout."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pytest

_PKG = Path(__file__).resolve().parents[1]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

os.environ.setdefault("HERMES_RESEARCH_SMOKE", "1")

from data_loader import load_bars
from signals import build_feature_frame


def test_heldout_feature_stability_across_tail():
    """Held-out: tail slice features remain finite and ordered."""
    bars = load_bars("AAPL", "5min")
    feat = build_feature_frame(bars)
    tail = feat.tail(40)
    assert len(tail) >= 20
    numeric = tail.select_dtypes(include=[np.number])
    assert np.isfinite(numeric.to_numpy()).all()
    assert tail["bar_end_utc"].is_monotonic_increasing


def test_heldout_purged_kfold_no_train_test_overlap():
    from purged_kfold import purged_kfold_splits

    bars = load_bars("AAPL", "5min")
    feat = build_feature_frame(bars)
    ts = feat["bar_end_utc"].to_numpy()
    folds = purged_kfold_splits(ts, n_splits=2, min_train_bars=80, test_bars=30)
    assert folds
    for train_idx, test_idx in folds:
        assert train_idx.max() < test_idx.min()
