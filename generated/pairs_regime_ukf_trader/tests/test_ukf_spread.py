"""Tests for UKF log-spread filter."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

_PKG = Path(__file__).resolve().parents[1]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

os.environ.setdefault("HERMES_RESEARCH_SMOKE", "1")

from regime_markov import RegimeState
from ukf_spread import REGIME_R_SCALE, UKFSpreadFilter, modulate_observation_noise


def _simulate_ou_spread(
    n: int = 300,
    *,
    kappa: float = 0.15,
    sigma: float = 0.03,
    seed: int = 7,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """OU log-spread with synthetic log prices for beta=1."""
    rng = np.random.default_rng(seed)
    spread = np.zeros(n, dtype=float)
    spread[0] = 0.6
    dt = 1.0
    for t in range(1, n):
        spread[t] = (
            spread[t - 1]
            - kappa * spread[t - 1] * dt
            + sigma * rng.normal() * np.sqrt(dt)
        )

    log_b = np.cumsum(rng.normal(0.0, 0.008, size=n))
    log_a = log_b + spread
    price_a = np.exp(log_a)
    price_b = np.exp(log_b)
    return spread, price_a, price_b


def test_synthetic_mean_reverting_spread_recovers_level():
    spread, price_a, price_b = _simulate_ou_spread()
    ukf = UKFSpreadFilter(beta=1.0)

    for pa, pb in zip(price_a, price_b):
        ukf.update(float(pa), float(pb))

    assert np.isfinite(ukf.spread_level)
    assert abs(ukf.spread_level - spread[-1]) < 0.15


def test_spread_z_is_innovation_over_sqrt_s():
    spread, price_a, price_b = _simulate_ou_spread(n=120, seed=19)
    ukf = UKFSpreadFilter(beta=1.0, observation_noise=1e-3)

    for pa, pb in zip(price_a, price_b):
        ukf.update(float(pa), float(pb))

    assert np.isfinite(ukf.spread_z)
    assert abs(ukf.spread_z) < 10.0


def test_regime_modulator_scales_observation_noise():
    base_r = 1e-4
    bull_r = modulate_observation_noise(base_r, RegimeState.BULL)
    volatile_r = modulate_observation_noise(base_r, RegimeState.VOLATILE)
    crash_r = modulate_observation_noise(base_r, RegimeState.CRASH)

    assert bull_r == base_r * REGIME_R_SCALE[RegimeState.BULL]
    assert volatile_r > bull_r
    assert crash_r > volatile_r


def test_cointegration_beta_sets_log_spread():
    rng = np.random.default_rng(11)
    log_b = np.cumsum(rng.normal(0.0, 0.01, size=40))
    beta = 2.0
    true_spread = 0.45
    log_a = beta * log_b + true_spread
    ukf = UKFSpreadFilter(beta=beta)
    for la, lb in zip(log_a, log_b):
        ukf.update(float(np.exp(la)), float(np.exp(lb)))

    assert abs(ukf.spread_level - true_spread) < 0.05


def test_regime_row_wires_into_filter():
    base_r = 1e-4
    row = {"regime_label": "CRASH", "regime_confidence": 0.9}
    ukf = UKFSpreadFilter(beta=1.0, observation_noise=base_r, regime_row=row)
    assert ukf._effective_R() == modulate_observation_noise(base_r, regime_row=row)


def test_velocity_tracks_spread_changes():
    spread, price_a, price_b = _simulate_ou_spread(n=200, seed=3)
    ukf = UKFSpreadFilter(beta=1.0)

    for pa, pb in zip(price_a, price_b):
        ukf.update(float(pa), float(pb))

    assert np.isfinite(ukf.velocity)
