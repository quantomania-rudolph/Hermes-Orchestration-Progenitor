"""Simulated portfolio NAV from OOS strategy returns (§10).

Compounds per-bar strategy returns into a normalized equity curve, tracks
turnover, exposure, drawdown, and an entry/exit trade log keyed by fold id.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from trading_loop import position_changes

__all__ = [
    "PortfolioBar",
    "PortfolioResult",
    "PortfolioState",
    "TradeLogEntry",
    "build_trade_log",
    "simulate_portfolio",
]


@dataclass
class PortfolioState:
    """Mutable portfolio snapshot during simulation."""

    cash: float = 1.0
    position: int = 0
    equity_curve: list[float] = field(default_factory=lambda: [1.0])


@dataclass(frozen=True)
class TradeLogEntry:
    """One completed or open round-trip segment."""

    fold_id: int | None
    entry_bar_end_utc: Any
    exit_bar_end_utc: Any | None
    direction: int
    pnl: float
    bars_held: int


@dataclass
class PortfolioBar:
    """Per-bar portfolio metrics aligned to the trading loop."""

    position: int
    strategy_return: float
    cum_nav: float
    drawdown: float


@dataclass
class PortfolioResult:
    """Simulated portfolio outputs for backtest reporting."""

    cum_nav: np.ndarray
    drawdown: np.ndarray
    strategy_return: np.ndarray
    position: np.ndarray
    turnover: float
    exposure_pct: float
    bars_in_market: int
    trade_log: list[TradeLogEntry]
    timestamps: np.ndarray | None = None
    fold_ids: np.ndarray | None = None


def simulate_portfolio(
    strategy_returns: np.ndarray,
    positions: np.ndarray,
    *,
    timestamps: np.ndarray | None = None,
    fold_ids: np.ndarray | None = None,
    initial_nav: float = 1.0,
) -> PortfolioResult:
    """
    Compound strategy returns into NAV and compute portfolio diagnostics.

    Parameters
    ----------
    strategy_returns
        Cost-adjusted per-bar returns from ``trading_loop.run_trading_loop``.
    positions
        Discrete positions in ``{-1, 0, 1}`` aligned to ``strategy_returns``.
    timestamps
        Optional ``bar_end_utc`` per bar for trade logging.
    fold_ids
        Optional fold id per bar; trade log segments reset at fold boundaries.
    initial_nav
        Starting normalized NAV (default 1.0).
    """
    rets = np.asarray(strategy_returns, dtype=np.float64)
    pos = np.asarray(positions, dtype=np.int8)
    if rets.shape != pos.shape:
        raise ValueError(
            f"strategy_returns and positions must share shape; "
            f"got {rets.shape} vs {pos.shape}"
        )
    if rets.ndim != 1:
        raise ValueError(f"strategy_returns must be 1-D, got shape {rets.shape}")

    n = rets.shape[0]
    if fold_ids is not None and np.asarray(fold_ids).shape[0] != n:
        raise ValueError("fold_ids length must match strategy_returns")
    if timestamps is not None and np.asarray(timestamps).shape[0] != n:
        raise ValueError("timestamps length must match strategy_returns")

    if n == 0:
        return PortfolioResult(
            cum_nav=np.array([], dtype=np.float64),
            drawdown=np.array([], dtype=np.float64),
            strategy_return=rets,
            position=pos,
            turnover=0.0,
            exposure_pct=0.0,
            bars_in_market=0,
            trade_log=[],
            timestamps=timestamps,
            fold_ids=fold_ids,
        )

    cum_nav = _compound_nav(rets, initial_nav=initial_nav)
    running_max = np.maximum.accumulate(cum_nav)
    drawdown = cum_nav - running_max

    turnover = float(np.sum(position_changes(pos, fold_ids=fold_ids)))
    exposure_pct = float(np.mean(np.abs(pos.astype(np.float64))))
    bars_in_market = int(np.count_nonzero(pos))

    trade_log = build_trade_log(
        pos,
        rets,
        timestamps=timestamps,
        fold_ids=fold_ids,
    )

    return PortfolioResult(
        cum_nav=cum_nav,
        drawdown=drawdown,
        strategy_return=rets,
        position=pos,
        turnover=turnover,
        exposure_pct=exposure_pct,
        bars_in_market=bars_in_market,
        trade_log=trade_log,
        timestamps=timestamps,
        fold_ids=fold_ids,
    )


def build_trade_log(
    positions: np.ndarray,
    strategy_returns: np.ndarray,
    *,
    timestamps: np.ndarray | None = None,
    fold_ids: np.ndarray | None = None,
) -> list[TradeLogEntry]:
    """
    Build entry/exit trade log from position path and per-bar returns.

    Segments close when position goes flat, flips sign, or a new fold begins.
    """
    pos = np.asarray(positions, dtype=np.int8)
    rets = np.asarray(strategy_returns, dtype=np.float64)
    ts = np.asarray(timestamps) if timestamps is not None else None
    folds = np.asarray(fold_ids, dtype=np.int64) if fold_ids is not None else None

    trades: list[TradeLogEntry] = []
    open_dir = 0
    open_fold: int | None = None
    open_ts: Any = None
    open_idx: int | None = None
    segment_rets: list[float] = []

    for i in range(pos.shape[0]):
        cur_fold = int(folds[i]) if folds is not None else None
        fold_break = folds is not None and open_dir != 0 and cur_fold != open_fold

        if fold_break:
            trades.append(
                TradeLogEntry(
                    fold_id=open_fold,
                    entry_bar_end_utc=open_ts,
                    exit_bar_end_utc=_bar_ts(ts, i - 1),
                    direction=open_dir,
                    pnl=float(np.sum(segment_rets)),
                    bars_held=len(segment_rets),
                )
            )
            open_dir = 0
            open_fold = None
            open_ts = None
            open_idx = None
            segment_rets = []

        cur_pos = int(pos[i])
        if open_dir == 0:
            if cur_pos != 0:
                open_dir = cur_pos
                open_fold = cur_fold
                open_ts = _bar_ts(ts, i)
                open_idx = i
                segment_rets = [float(rets[i])]
            continue

        if cur_pos == open_dir:
            segment_rets.append(float(rets[i]))
            continue

        trades.append(
            TradeLogEntry(
                fold_id=open_fold,
                entry_bar_end_utc=open_ts,
                exit_bar_end_utc=_bar_ts(ts, i - 1),
                direction=open_dir,
                pnl=float(np.sum(segment_rets)),
                bars_held=len(segment_rets),
            )
        )
        open_dir = 0
        open_fold = None
        open_ts = None
        open_idx = None
        segment_rets = []

        if cur_pos != 0:
            open_dir = cur_pos
            open_fold = cur_fold
            open_ts = _bar_ts(ts, i)
            open_idx = i
            segment_rets = [float(rets[i])]

    if open_dir != 0 and segment_rets:
        exit_i = open_idx if open_idx is not None else pos.shape[0] - 1
        trades.append(
            TradeLogEntry(
                fold_id=open_fold,
                entry_bar_end_utc=open_ts,
                exit_bar_end_utc=_bar_ts(ts, exit_i + len(segment_rets) - 1),
                direction=open_dir,
                pnl=float(np.sum(segment_rets)),
                bars_held=len(segment_rets),
            )
        )

    return trades


def _compound_nav(returns: np.ndarray, *, initial_nav: float = 1.0) -> np.ndarray:
    growth = 1.0 + returns
    growth = np.where(np.isfinite(growth), growth, 1.0)
    nav = initial_nav * np.cumprod(growth)
    return nav


def _bar_ts(timestamps: np.ndarray | None, idx: int) -> Any:
    if timestamps is None:
        return None
    if idx < 0 or idx >= timestamps.shape[0]:
        return None
    val = timestamps[idx]
    if isinstance(val, np.datetime64):
        return str(np.datetime_as_string(val, unit="s"))
    return val
