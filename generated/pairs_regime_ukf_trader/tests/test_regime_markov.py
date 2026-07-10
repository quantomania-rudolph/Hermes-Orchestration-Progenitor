"""Tests for anti-flicker four-state Markov regime filter."""

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

from regime_markov import (
    FEATURE_COLS,
    MIN_REGIME_BARS,
    POSTERIOR_EMA_ALPHA,
    SWITCH_COMMIT_PROB,
    RegimeState,
    build_regime_features,
    filter_regime,
    fit_regime_model,
)


def _planted_features(
    n: int = 200,
    *,
    segment: int = 50,
    seed: int = 11,
    noise_scale: float = 0.35,
) -> pd.DataFrame:
    """Synthetic features with long planted regime segments and additive noise."""
    rng = np.random.default_rng(seed)
    regime_order = [RegimeState.BULL, RegimeState.BEAR, RegimeState.VOLATILE, RegimeState.CRASH]
    means = {
        RegimeState.BULL: np.array([0.015, 0.12, 0.01, -0.005, 0.35]),
        RegimeState.BEAR: np.array([-0.010, 0.18, 0.06, -0.020, 0.42]),
        RegimeState.VOLATILE: np.array([0.000, 0.28, 0.10, -0.030, 0.62]),
        RegimeState.CRASH: np.array([-0.070, 0.35, 0.28, -0.080, 0.75]),
    }

    rows: list[np.ndarray] = []
    for i in range(n):
        seg_idx = min(i // segment, len(regime_order) - 1)
        state = regime_order[seg_idx]
        base = means[state]
        noise = rng.normal(0.0, noise_scale, size=len(FEATURE_COLS))
        noise *= np.array([0.004, 0.02, 0.015, 0.006, 0.04])
        rows.append(base + noise)

    return pd.DataFrame(rows, columns=list(FEATURE_COLS))


def _count_switches(labels: pd.Series) -> int:
    arr = labels.to_numpy()
    if len(arr) <= 1:
        return 0
    return int(np.sum(arr[1:] != arr[:-1]))


def _max_switches_per_window(labels: pd.Series, window: int = 50) -> int:
    arr = labels.to_numpy()
    if len(arr) < window:
        return _count_switches(labels)
    worst = 0
    for start in range(0, len(arr) - window + 1):
        segment = arr[start : start + window]
        switches = int(np.sum(segment[1:] != segment[:-1]))
        worst = max(worst, switches)
    return worst


def test_regime_state_enum():
    assert RegimeState.BULL.value == 0
    assert RegimeState.CRASH.name == "CRASH"
    assert len(RegimeState) == 4


def test_build_regime_features_columns():
    idx = pd.date_range("2024-01-01", periods=60, freq="D")
    ret = pd.Series(np.random.default_rng(3).normal(0.0, 0.01, len(idx)), index=idx)
    feat = build_regime_features(ret)
    assert list(feat.columns) == list(FEATURE_COLS)
    assert len(feat) == len(ret)


def test_filter_regime_output_schema():
    features = _planted_features(n=120, noise_scale=0.25)
    fit_regime_model(features.iloc[:80])
    out = filter_regime(features)

    assert "regime_label" in out.columns
    assert "regime_confidence" in out.columns
    for label in ("BULL", "BEAR", "VOLATILE", "CRASH"):
        assert f"regime_prob_{label}" in out.columns
    assert set(out["regime_label"].unique()).issubset({"BULL", "BEAR", "VOLATILE", "CRASH"})
    assert (out["regime_confidence"] >= 0.0).all() and (out["regime_confidence"] <= 1.0).all()


def test_planted_regime_antiflicker_under_noise():
    """Filtered labels must not flicker more than 2 switches per 50 bars."""
    features = _planted_features(n=200, segment=50, noise_scale=0.40)
    fit_regime_model(features.iloc[:100])
    filtered = filter_regime(features)

    max_switches = _max_switches_per_window(filtered["regime_label"], window=50)
    assert max_switches <= 2, (
        f"anti-flicker violated: {max_switches} switches in a 50-bar window "
        f"(min_dwell={MIN_REGIME_BARS}, alpha={POSTERIOR_EMA_ALPHA}, "
        f"commit={SWITCH_COMMIT_PROB})"
    )


def test_minimum_dwell_respected():
    features = _planted_features(n=160, segment=40, noise_scale=0.50)
    fit_regime_model(features)
    filtered = filter_regime(features)
    labels = filtered["regime_label"].to_numpy()

    run = 1
    for i in range(1, len(labels)):
        if labels[i] == labels[i - 1]:
            run += 1
        else:
            assert run >= MIN_REGIME_BARS or i < MIN_REGIME_BARS
            run = 1
