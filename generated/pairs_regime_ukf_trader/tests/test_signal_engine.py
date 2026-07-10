"""Tests for regime-modulated UKF spread signals."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Mapping

_PKG = Path(__file__).resolve().parents[1]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

os.environ.setdefault("HERMES_RESEARCH_SMOKE", "1")

import signal_engine
from regime_markov import RegimeState
from threshold_modulator import compute_thresholds, modulate
from ukf_spread import UKFSpreadFilter


class _StubUKF:
    """Minimal UKF stand-in with a fixed post-update spread_z."""

    def __init__(self, spread_z: float) -> None:
        self._spread_z = float(spread_z)

    @property
    def spread_z(self) -> float:
        return self._spread_z

    def set_regime(
        self,
        regime_label: str | None = None,
        *,
        regime_confidence: float | None = None,
        regime_row: Mapping[str, Any] | None = None,
    ) -> None:
        return None

    def update(self, price_a: float, price_b: float) -> None:
        return None


_PAIR = {"symbol_a": "AAPL", "symbol_b": "MSFT", "beta": 1.0}
_BAR = {"AAPL": 150.0, "MSFT": 300.0}


def _bull_row(confidence: float = 1.0) -> dict[str, Any]:
    return {"regime_label": RegimeState.BULL.name, "regime_confidence": confidence}


def _crash_row(confidence: float) -> dict[str, Any]:
    return {"regime_label": RegimeState.CRASH.name, "regime_confidence": confidence}


def setup_function() -> None:
    signal_engine.reset_positions()


def test_run_bar_returns_signal_schema():
    thresholds = compute_thresholds(RegimeState.BULL, 1.0)
    ukf = _StubUKF(-(thresholds["entry_z"] + 0.5))
    out = signal_engine.run_bar(_PAIR, _BAR, _bull_row(), ukf)
    assert set(out.keys()) == {"side", "size", "reason"}


def test_long_entry_when_spread_z_below_negative_entry_z():
    thresholds = compute_thresholds(RegimeState.BULL, 1.0)
    entry_z = float(thresholds["entry_z"])
    ukf = _StubUKF(-(entry_z + 0.2))

    out = signal_engine.run_bar(_PAIR, _BAR, _bull_row(), ukf)

    assert out["side"] == "long"
    assert out["reason"] == "entry"
    assert out["size"] > 0.0


def test_short_entry_when_spread_z_above_entry_z():
    thresholds = compute_thresholds(RegimeState.BULL, 1.0)
    entry_z = float(thresholds["entry_z"])
    ukf = _StubUKF(entry_z + 0.2)

    out = signal_engine.run_bar(_PAIR, _BAR, _bull_row(), ukf)

    assert out["side"] == "short"
    assert out["reason"] == "entry"
    assert out["size"] > 0.0


def test_exit_when_abs_spread_z_below_exit_z():
    thresholds = compute_thresholds(RegimeState.BULL, 1.0)
    entry_z = float(thresholds["entry_z"])
    exit_z = float(thresholds["exit_z"])

    signal_engine.run_bar(_PAIR, _BAR, _bull_row(), _StubUKF(-(entry_z + 0.3)))
    out = signal_engine.run_bar(_PAIR, _BAR, _bull_row(), _StubUKF(exit_z * 0.5))

    assert out["side"] == "flat"
    assert out["reason"] == "exit"
    assert out["size"] == 0.0


def test_stop_when_abs_spread_z_above_stop_z():
    thresholds = compute_thresholds(RegimeState.BULL, 1.0)
    entry_z = float(thresholds["entry_z"])
    stop_z = float(thresholds["stop_z"])

    signal_engine.run_bar(_PAIR, _BAR, _bull_row(), _StubUKF(entry_z + 0.3))
    out = signal_engine.run_bar(_PAIR, _BAR, _bull_row(), _StubUKF(stop_z + 0.5))

    assert out["side"] == "flat"
    assert out["reason"] == "stop"
    assert out["size"] == 0.0


def test_blocks_entry_on_low_confidence_crash():
    thresholds = compute_thresholds(RegimeState.CRASH, 0.5)
    entry_z = float(thresholds["entry_z"])
    ukf = _StubUKF(-(entry_z + 1.0))

    out = signal_engine.run_bar(_PAIR, _BAR, _crash_row(0.5), ukf)

    mods = modulate(ukf.spread_z, _crash_row(0.5))
    assert mods["block_entry"] is True
    assert out["side"] == "flat"
    assert out["reason"] == "blocked"
    assert out["size"] == 0.0


def test_position_size_scales_with_confidence():
    confidence = 0.8
    thresholds = compute_thresholds(RegimeState.BULL, confidence)
    entry_z = float(thresholds["entry_z"])
    expected = signal_engine.BASE_NOTIONAL * float(thresholds["position_cap_frac"]) * confidence

    out = signal_engine.run_bar(
        _PAIR,
        _BAR,
        _bull_row(confidence),
        _StubUKF(-(entry_z + 0.2)),
    )

    assert out["reason"] == "entry"
    assert abs(out["size"] - expected) < 1e-6


def test_hold_when_flat_and_inside_bands():
    thresholds = compute_thresholds(RegimeState.BULL, 1.0)
    entry_z = float(thresholds["entry_z"])
    ukf = _StubUKF(entry_z * 0.5)

    out = signal_engine.run_bar(_PAIR, _BAR, _bull_row(), ukf)

    assert out["side"] == "flat"
    assert out["reason"] == "hold"
    assert out["size"] == 0.0


def test_run_bar_with_real_ukf_first_bar_is_hold():
    """First UKF update initializes state; spread_z=0 cannot trigger entry."""
    ukf = UKFSpreadFilter(beta=float(_PAIR["beta"]))
    out = signal_engine.run_bar(_PAIR, _BAR, _bull_row(), ukf)

    assert set(out.keys()) == {"side", "size", "reason"}
    assert out["side"] == "flat"
    assert out["reason"] == "hold"
    assert out["size"] == 0.0
