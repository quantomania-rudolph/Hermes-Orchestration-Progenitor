"""Regime-dependent z-score threshold and position cap modulation."""

from __future__ import annotations

from typing import Any, Mapping

import config as cfg
from regime_markov import RegimeState, regime_state_from_label

def _crash_min_confidence() -> float:
    return float(
        getattr(cfg, "REGIME_PARAMS", {}).get("CRASH", {}).get("min_regime_confidence", 0.7)
    )

VOL_PENALTY: dict[RegimeState, float] = {
    RegimeState.BULL: 0.0,
    RegimeState.BEAR: 0.05,
    RegimeState.VOLATILE: 0.15,
    RegimeState.CRASH: 0.25,
}

REGIME_PARAMS: dict[RegimeState, dict[str, float | bool]] = {
    RegimeState.BULL: {
        "entry_z": 1.6,
        "exit_z": 0.4,
        "stop_z": 3.2,
        "position_cap_frac": 1.0,
        "allow_new_entries": True,
    },
    RegimeState.BEAR: {
        "entry_z": 2.0,
        "exit_z": 0.5,
        "stop_z": 4.0,
        "position_cap_frac": 0.7,
        "allow_new_entries": True,
    },
    RegimeState.VOLATILE: {
        "entry_z": 2.8,
        "exit_z": 0.8,
        "stop_z": 5.6,
        "position_cap_frac": 0.5,
        "allow_new_entries": True,
    },
    RegimeState.CRASH: {
        "entry_z": 3.5,
        "exit_z": 1.2,
        "stop_z": 7.0,
        "position_cap_frac": 0.25,
        "allow_new_entries": True,
    },
}


def _clamp_confidence(confidence: float) -> float:
    return float(max(0.0, min(1.0, confidence)))


def _lerp(a: float, b: float, weight: float) -> float:
    return float(a * weight + b * (1.0 - weight))


def _coerce_regime_state(regime_label: str | RegimeState) -> RegimeState:
    """Normalize enum members across importlib.reload boundaries."""
    if isinstance(regime_label, RegimeState):
        return RegimeState(regime_label.value)
    return regime_state_from_label(str(regime_label))


def compute_thresholds(
    regime_label: str | RegimeState,
    regime_confidence: float,
) -> dict[str, float | bool]:
    """Interpolate toward VOLATILE params when confidence is low, then scale thresholds."""
    state = _coerce_regime_state(regime_label)
    confidence = _clamp_confidence(regime_confidence)
    base = REGIME_PARAMS[state]
    volatile = REGIME_PARAMS[RegimeState.VOLATILE]

    entry_z = _lerp(float(base["entry_z"]), float(volatile["entry_z"]), confidence)
    exit_z = _lerp(float(base["exit_z"]), float(volatile["exit_z"]), confidence)
    stop_z = _lerp(float(base["stop_z"]), float(volatile["stop_z"]), confidence)
    position_cap_frac = _lerp(
        float(base["position_cap_frac"]),
        float(volatile["position_cap_frac"]),
        confidence,
    )

    threshold_scale = 1.0 + VOL_PENALTY[state] + (1.0 - confidence) * 0.5
    entry_z *= threshold_scale
    exit_z *= threshold_scale
    stop_z *= threshold_scale

    allow_new_entries = bool(base["allow_new_entries"])
    if state == RegimeState.CRASH and confidence < _crash_min_confidence():
        allow_new_entries = False

    return {
        "entry_z": entry_z,
        "exit_z": exit_z,
        "stop_z": stop_z,
        "position_cap_frac": position_cap_frac,
        "allow_new_entries": allow_new_entries,
    }


def modulate(
    spread_z: float,
    regime_row: Mapping[str, Any],
) -> dict[str, float | bool]:
    """Return regime-modulated thresholds and entry gate for a single bar."""
    label = regime_row.get("regime_label", RegimeState.BULL.name)
    confidence = float(regime_row.get("regime_confidence", 1.0))
    thresholds = compute_thresholds(label, confidence)

    block_entry = not bool(thresholds["allow_new_entries"])
    size_cap = float(thresholds["position_cap_frac"]) * min(1.0, confidence)

    return {
        "entry_z": float(thresholds["entry_z"]),
        "exit_z": float(thresholds["exit_z"]),
        "size_cap": size_cap,
        "block_entry": block_entry,
    }
