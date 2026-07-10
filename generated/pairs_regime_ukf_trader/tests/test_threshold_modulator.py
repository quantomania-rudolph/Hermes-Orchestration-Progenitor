"""Tests for regime-dependent threshold modulation."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_PKG = Path(__file__).resolve().parents[1]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

os.environ.setdefault("HERMES_RESEARCH_SMOKE", "1")

from regime_markov import RegimeState
from threshold_modulator import REGIME_PARAMS, VOL_PENALTY, compute_thresholds, modulate

_REGIME_ORDER = (
    RegimeState.BULL,
    RegimeState.BEAR,
    RegimeState.VOLATILE,
    RegimeState.CRASH,
)


def _thresholds_at_full_confidence(state: RegimeState) -> dict[str, float | bool]:
    return compute_thresholds(state, 1.0)


def test_regime_params_schema():
    required = {"entry_z", "exit_z", "stop_z", "position_cap_frac", "allow_new_entries"}
    for state in _REGIME_ORDER:
        assert state in REGIME_PARAMS
        assert required.issubset(REGIME_PARAMS[state].keys())


def test_entry_exit_stop_monotonic_at_full_confidence():
    entry_vals = [_thresholds_at_full_confidence(s)["entry_z"] for s in _REGIME_ORDER]
    exit_vals = [_thresholds_at_full_confidence(s)["exit_z"] for s in _REGIME_ORDER]
    stop_vals = [_thresholds_at_full_confidence(s)["stop_z"] for s in _REGIME_ORDER]

    assert entry_vals == sorted(entry_vals)
    assert exit_vals == sorted(exit_vals)
    assert stop_vals == sorted(stop_vals)
    assert entry_vals[0] == _thresholds_at_full_confidence(RegimeState.BULL)["entry_z"]
    assert entry_vals[-1] == _thresholds_at_full_confidence(RegimeState.CRASH)["entry_z"]


def test_position_cap_monotonic_at_full_confidence():
    caps = [_thresholds_at_full_confidence(s)["position_cap_frac"] for s in _REGIME_ORDER]
    assert caps == sorted(caps, reverse=True)
    assert caps[0] == _thresholds_at_full_confidence(RegimeState.BULL)["position_cap_frac"]
    assert caps[-1] == _thresholds_at_full_confidence(RegimeState.CRASH)["position_cap_frac"]


def test_bull_tightest_crash_widest_entry_z():
    bull = _thresholds_at_full_confidence(RegimeState.BULL)["entry_z"]
    crash = _thresholds_at_full_confidence(RegimeState.CRASH)["entry_z"]
    for state in (RegimeState.BEAR, RegimeState.VOLATILE):
        mid = _thresholds_at_full_confidence(state)["entry_z"]
        assert bull < mid < crash


def test_low_confidence_interpolates_toward_volatile():
    bull_high = compute_thresholds(RegimeState.BULL, 1.0)["entry_z"]
    bull_low = compute_thresholds(RegimeState.BULL, 0.0)["entry_z"]
    volatile_base = float(REGIME_PARAMS[RegimeState.VOLATILE]["entry_z"])
    expected_low = volatile_base * (1.0 + VOL_PENALTY[RegimeState.BULL] + 0.5)
    assert bull_low > bull_high
    assert abs(bull_low - expected_low) < 1e-9


def test_modulate_returns_expected_keys():
    row = {"regime_label": "BULL", "regime_confidence": 0.9}
    out = modulate(1.5, row)
    assert set(out.keys()) == {"entry_z", "exit_z", "size_cap", "block_entry"}
    assert out["entry_z"] > 0.0
    assert out["exit_z"] > 0.0
    assert 0.0 < out["size_cap"] <= 1.0


def test_modulate_blocks_low_confidence_crash():
    row = {"regime_label": "CRASH", "regime_confidence": 0.5}
    out = modulate(2.0, row)
    assert out["block_entry"] is True


def test_modulate_allows_high_confidence_crash():
    row = {"regime_label": "CRASH", "regime_confidence": 0.85}
    out = modulate(2.0, row)
    assert out["block_entry"] is False
