"""Minimal deterministic backtest scaffold for DAEDALUS trading-performance hooks (P5-001).

Provides a measurable ``performance_objective()`` scalar for E0 grounding and
R05 performance anchors. Uses ``signal_model`` + ``data_loader`` offline fixtures.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def run_backtest(symbol: str = "AAPL", interval: str = "5min") -> dict[str, float]:
    """Run a simple signal-following backtest on loaded bars."""
    from data_loader import load_bars
    from signal_model import generate_signals

    bars = load_bars(symbol=symbol, interval=interval)
    if bars.empty or len(bars) < 20:
        return {"total_return": 0.0, "sharpe": 0.0, "n_trades": 0.0}

    signals = generate_signals(bars)
    ret = bars["close"].pct_change().fillna(0.0)
    position = signals.shift(1).fillna(0).astype(float)
    pnl = float((position * ret).sum())
    n_trades = float((signals.diff().abs() > 0).sum())
    vol = float(ret.std()) or 1e-9
    sharpe = pnl / (vol * (len(ret) ** 0.5)) if vol > 0 else 0.0
    return {"total_return": pnl, "sharpe": float(sharpe), "n_trades": n_trades}


def performance_objective() -> float:
    """Scalar hook wired into E0 graph sites / metric synthesis (verify-friendly)."""
    return float(run_backtest().get("total_return", 0.0))


def verify() -> dict[str, Any]:
    """Deterministic self-check for verification harnesses."""
    metrics = run_backtest()
    ok = all(
        isinstance(metrics.get(k), (int, float)) and pd.notna(metrics.get(k))
        for k in ("total_return", "sharpe", "n_trades")
    )
    return {"ok": ok, "metrics": metrics, "performance_objective": performance_objective()}
