"""Regime-modulated UKF spread signal engine (research only)."""

from __future__ import annotations

from typing import Any, Mapping

import config as cfg
from threshold_modulator import compute_thresholds, modulate
from ukf_spread import UKFSpreadFilter

BASE_NOTIONAL = float(getattr(cfg, "BASE_NOTIONAL", 100_000.0))

_positions: dict[str, str] = {}


def _pair_key(pair: Mapping[str, Any]) -> str:
    return f"{pair['symbol_a']}:{pair['symbol_b']}"


def _extract_close(bar: Mapping[str, Any], symbol: str) -> float:
    """Resolve a symbol close price from flexible bar shapes."""
    if symbol in bar:
        value = bar[symbol]
        if isinstance(value, Mapping):
            if "close" not in value:
                raise KeyError(f"bar[{symbol!r}] missing 'close'")
            return float(value["close"])
        return float(value)

    nested = bar.get("close")
    if isinstance(nested, Mapping) and symbol in nested:
        return float(nested[symbol])

    keyed = (symbol, "close")
    if keyed in bar:
        return float(bar[keyed])

    raise KeyError(f"bar missing close price for {symbol!r}")


def reset_positions() -> None:
    """Clear tracked open positions (useful for backtest folds and tests)."""
    _positions.clear()


def run_bar(
    pair: Mapping[str, Any],
    bar: Mapping[str, Any],
    regime_row: Mapping[str, Any],
    ukf: UKFSpreadFilter,
) -> dict[str, Any]:
    """Update UKF on the bar and emit a regime-gated spread signal."""
    symbol_a = str(pair["symbol_a"])
    symbol_b = str(pair["symbol_b"])
    price_a = _extract_close(bar, symbol_a)
    price_b = _extract_close(bar, symbol_b)

    ukf.set_regime(regime_label=None, regime_row=regime_row)
    ukf.update(price_a, price_b)

    spread_z = float(ukf.spread_z)
    mods = modulate(spread_z, regime_row)
    entry_z = float(mods["entry_z"])
    exit_z = float(mods["exit_z"])
    block_entry = bool(mods["block_entry"])

    label = regime_row.get("regime_label", "BULL")
    confidence = float(regime_row.get("regime_confidence", 1.0))
    stop_z = float(compute_thresholds(label, confidence)["stop_z"])

    notional = BASE_NOTIONAL * float(mods["size_cap"])
    pair_key = _pair_key(pair)
    position = _positions.get(pair_key, "flat")
    abs_z = abs(spread_z)

    if position != "flat":
        if abs_z > stop_z:
            _positions[pair_key] = "flat"
            return {"side": "flat", "size": 0.0, "reason": "stop"}
        if abs_z < exit_z:
            _positions[pair_key] = "flat"
            return {"side": "flat", "size": 0.0, "reason": "exit"}
        return {"side": position, "size": 0.0, "reason": "hold"}

    if block_entry:
        return {"side": "flat", "size": 0.0, "reason": "blocked"}

    if spread_z < -entry_z:
        _positions[pair_key] = "long"
        return {"side": "long", "size": notional, "reason": "entry"}

    if spread_z > entry_z:
        _positions[pair_key] = "short"
        return {"side": "short", "size": notional, "reason": "entry"}

    return {"side": "flat", "size": 0.0, "reason": "hold"}
