"""Tests for pair discovery on synthetic cointegrated series."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PKG = Path(__file__).resolve().parents[1]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

os.environ.setdefault("HERMES_RESEARCH_SMOKE", "1")

from pair_selection import (
    MIN_OVERLAP_BARS,
    PairCandidate,
    clayton_copula_theta,
    engle_granger_cointegration,
    gaussian_copula_tail_dependence,
    rank_pairs,
    rolling_pearson_matrix,
    rolling_spearman_matrix,
)


def _synthetic_cointegrated_returns(
    n: int = 400,
    *,
    seed: int = 7,
    beta: float = 1.2,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x = np.cumsum(rng.normal(0.0, 0.01, n))
    spread = np.zeros(n)
    for t in range(1, n):
        spread[t] = 0.85 * spread[t - 1] + rng.normal(0.0, 0.015)
    y = beta * x + spread
    returns = pd.DataFrame(
        {
            "LEG_A": np.diff(y),
            "LEG_B": np.diff(x),
            "DECOY": rng.normal(0.0, 0.02, n - 1),
        }
    )
    return returns


def test_rolling_correlation_matrices():
    returns = _synthetic_cointegrated_returns()
    levels = returns.cumsum()
    pearson = rolling_pearson_matrix(levels, window=120)
    spearman = rolling_spearman_matrix(levels, window=120)

    assert pearson.shape == (3, 3)
    assert spearman.shape == (3, 3)
    assert pearson.loc["LEG_A", "LEG_B"] == pearson.loc["LEG_B", "LEG_A"]
    assert abs(pearson.loc["LEG_A", "LEG_B"]) > 0.65


def test_engle_granger_on_cointegrated_levels():
    n = 500
    rng = np.random.default_rng(11)
    x = np.cumsum(rng.normal(0.0, 0.01, n))
    y = 1.5 * x + rng.normal(0.0, 0.05, n)
    pvalue, beta = engle_granger_cointegration(y, x)

    assert pvalue < 0.05
    assert np.isfinite(beta)
    assert abs(beta - 1.5) < 0.25


def test_copula_helpers_on_correlated_uniforms():
    rng = np.random.default_rng(3)
    u = rng.uniform(0.0, 1.0, 300)
    v = np.clip(u + rng.normal(0.0, 0.08, 300), 0.001, 0.999)

    tail = gaussian_copula_tail_dependence(u, v)
    theta = clayton_copula_theta(u, v)

    assert 0.0 <= tail <= 1.0
    assert theta >= 0.0


def test_rank_pairs_selects_cointegrated_candidate():
    returns = _synthetic_cointegrated_returns(n=450, seed=21)
    ranked = rank_pairs(returns, window=120, max_pairs=5)

    assert ranked
    assert all(isinstance(item, PairCandidate) for item in ranked)
    top = ranked[0]
    assert {top.symbol_a, top.symbol_b} == {"LEG_A", "LEG_B"}
    assert abs(top.corr) > 0.65
    assert top.coint_p < 0.05
    assert 0.0 <= top.tail_dep <= 1.0
    assert top.score >= ranked[-1].score


def test_rank_pairs_respects_min_overlap_bars():
    short = _synthetic_cointegrated_returns(n=MIN_OVERLAP_BARS - 1, seed=5)
    assert rank_pairs(short) == []
