"""Leakage guards: one-bar feature shift and train-only pair scores."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_PKG = Path(__file__).resolve().parents[1]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

os.environ.setdefault("HERMES_RESEARCH_SMOKE", "1")

from data_loader import load_universe_bars
from purged_splits import adaptive_split_params, expanding_purged_splits
from regime_markov import FEATURE_COLS, build_regime_features
from run_pipeline import (
    LeakageError,
    assert_features_shifted_one_bar,
    assert_no_leakage,
    assert_pair_scores_train_only,
    audit_leakage_folds,
    corr_median_series,
    eigen_concentration_series,
    leakage_safe_regime_features,
)


def _log_returns_from_bars(bars: pd.DataFrame) -> pd.DataFrame:
    close = bars.xs("close", axis=1, level=1).astype(float)
    return (
        np.log(close / close.shift(1))
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
    )


def test_unshifted_regime_features_rejected():
    bars = load_universe_bars()
    log_returns = _log_returns_from_bars(bars)
    market = log_returns.mean(axis=1)
    corr = corr_median_series(log_returns)
    eigen = eigen_concentration_series(log_returns)
    raw = build_regime_features(
        market,
        corr_median=corr,
        eigen_concentration=eigen,
    )
    with pytest.raises(LeakageError, match="shift"):
        assert_features_shifted_one_bar(
            raw,
            market,
            corr_median=corr,
            eigen_concentration=eigen,
        )


def test_regime_features_shifted_one_bar_minimum():
    bars = load_universe_bars()
    log_returns = _log_returns_from_bars(bars)
    market = log_returns.mean(axis=1)
    corr = corr_median_series(log_returns)
    eigen = eigen_concentration_series(log_returns)
    raw = build_regime_features(
        market,
        corr_median=corr,
        eigen_concentration=eigen,
    )
    shifted = leakage_safe_regime_features(
        market,
        corr_median=corr,
        eigen_concentration=eigen,
    )
    assert list(shifted.columns) == list(FEATURE_COLS)
    assert_features_shifted_one_bar(
        shifted,
        market,
        corr_median=corr,
        eigen_concentration=eigen,
    )
    # First bar must be NaN after shift; at least one later bar must be populated.
    assert shifted.iloc[1:].notna().any().any()


def test_pair_scores_use_train_window_only():
    bars = load_universe_bars()
    log_returns = _log_returns_from_bars(bars)
    params = adaptive_split_params(len(log_returns))
    folds = expanding_purged_splits(len(log_returns), **params)
    for train_idx, test_idx in folds:
        train_returns = log_returns.iloc[train_idx]
        test_returns = log_returns.iloc[test_idx]
        assert int(train_idx.max()) < int(test_idx.min())
        assert_pair_scores_train_only(train_returns, test_returns)


def test_purged_folds_pass_leakage_audit():
    bars = load_universe_bars()
    log_returns = _log_returns_from_bars(bars)
    params = adaptive_split_params(len(log_returns))
    folds = expanding_purged_splits(len(log_returns), **params)
    manifest = audit_leakage_folds(log_returns, folds)
    assert manifest["feature_shift_bars"] >= 1
    assert manifest["pair_scores_train_only"] is True
    assert manifest["folds_audited"] == len(folds)
    for fold in manifest["folds"]:
        assert fold["pair_count_train"] > 0, "train fold must rank at least one pair"


def test_assert_no_leakage_entrypoint():
    assert_no_leakage()
