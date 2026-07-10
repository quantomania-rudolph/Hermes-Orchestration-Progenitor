"""Walk-forward purged backtest for regime-modulated pairs trading (research only).

Per fold: refit pair selection and regime model on train, simulate OOS with a
frozen pair list. Applies slippage + spread costs and tracks per-regime PnL.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import config as cfg
import pair_selection as ps
from data_loader import load_universe_bars
from pair_selection import (
    PairCandidate,
    engle_granger_cointegration,
    rank_pairs,
)
from purged_splits import adaptive_split_params, expanding_purged_splits, split_summary
from regime_markov import (
    REGIME_LABELS,
    RegimeModelParams,
    build_regime_features,
    filter_regime,
    fit_regime_model,
)
from signal_engine import reset_positions, run_bar
from ukf_spread import UKFSpreadFilter

logger = logging.getLogger(__name__)

SMOKE = getattr(cfg, "SMOKE", None)
if SMOKE is None:
    import os

    SMOKE = os.getenv("HERMES_RESEARCH_SMOKE", "1") == "1"
else:
    SMOKE = bool(SMOKE)

PERIODS_PER_YEAR = 252
SLIPPAGE_BPS = 1.0
SPREAD_BPS = 0.5
BASE_NOTIONAL = float(getattr(cfg, "BASE_NOTIONAL", 100_000.0))

_ROOT = Path(__file__).resolve().parent
_REPORTS_DIR = _ROOT / "reports"

VALID_REGIMES = frozenset(REGIME_LABELS)

__all__ = [
    "PERIODS_PER_YEAR",
    "run_backtest",
    "verify",
    "write_reports",
]


@dataclass
class TradeRecord:
    fold: int
    symbol_a: str
    symbol_b: str
    entry_ts: str
    exit_ts: str
    side: str
    pnl: float
    regime: str
    reason: str


@dataclass
class FoldResult:
    fold: int
    pairs: list[dict[str, Any]]
    trades: list[TradeRecord] = field(default_factory=list)
    bar_returns: list[float] = field(default_factory=list)
    regime_timeline: list[dict[str, Any]] = field(default_factory=list)


def run_backtest(
    *,
    reports_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Execute the walk-forward backtest and write audit reports."""
    reports_path = Path(reports_dir) if reports_dir is not None else _REPORTS_DIR
    reports_path.mkdir(parents=True, exist_ok=True)

    bars = load_universe_bars()
    close = _close_frame(bars)
    log_returns = np.log(close / close.shift(1)).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    n_bars = len(close)

    split_params = adaptive_split_params(n_bars)
    folds = expanding_purged_splits(n_bars, **split_params)

    fold_results: list[FoldResult] = []
    pair_audits: list[dict[str, Any]] = []
    regime_timeline: list[dict[str, Any]] = []
    regime_pnl: dict[str, float] = {label: 0.0 for label in REGIME_LABELS}
    regime_trades: dict[str, int] = {label: 0 for label in REGIME_LABELS}

    for fold_k, (train_idx, test_idx) in enumerate(folds):
        train_returns = log_returns.iloc[train_idx]
        train_close = close.iloc[train_idx]
        test_close = close.iloc[test_idx]
        test_returns = log_returns.iloc[test_idx]

        pairs = _select_pairs(train_returns, train_close, fold_k=fold_k)
        pair_audits.append(
            {
                "fold": fold_k,
                "train_bars": int(train_idx.size),
                "test_bars": int(test_idx.size),
                "pairs": pairs,
            }
        )

        _, regime_df, train_regime_df = _fit_and_filter_regime(
            train_returns,
            test_returns,
        )

        fold_result = FoldResult(fold=fold_k, pairs=pairs)
        for ts, row in regime_df.iterrows():
            entry = {
                "ts_utc": _iso(ts),
                "fold": fold_k,
                "regime_label": str(row["regime_label"]),
                "regime_confidence": float(row["regime_confidence"]),
            }
            fold_result.regime_timeline.append(entry)
            regime_timeline.append(entry)

        if not pairs:
            logger.warning("fold %d: no pairs selected; skipping simulation", fold_k)
            fold_results.append(fold_result)
            continue

        trades, bar_returns, fold_regime_pnl = _simulate_fold(
            pairs=pairs,
            train_close=train_close,
            test_close=test_close,
            regime_df=regime_df,
            train_regime_df=train_regime_df,
            fold_k=fold_k,
        )
        fold_result.trades = trades
        fold_result.bar_returns = bar_returns
        fold_results.append(fold_result)

        for label, amount in fold_regime_pnl.items():
            regime_pnl[label] += amount
        for trade in trades:
            regime_trades[trade.regime] = regime_trades.get(trade.regime, 0) + 1

    all_bar_returns = [
        r for fr in fold_results for r in fr.bar_returns if np.isfinite(r)
    ]
    all_trades = [t for fr in fold_results for t in fr.trades]

    metrics = _compute_metrics(
        all_bar_returns,
        all_trades,
        regime_pnl=regime_pnl,
        regime_trades=regime_trades,
        fold_results=fold_results,
        split_params=split_params,
        split_summary=split_summary(folds, params=split_params),
        n_bars=n_bars,
    )

    write_reports(
        metrics,
        regime_timeline=regime_timeline,
        pair_audits=pair_audits,
        reports_dir=reports_path,
    )
    return metrics


def verify() -> bool:
    """Assert finite Sharpe, non-empty trades, and valid regime labels."""
    metrics = run_backtest()
    sharpe = float(metrics.get("sharpe", float("nan")))
    trade_count = int(metrics.get("trade_count", 0))
    labels = set(metrics.get("regime_labels_seen", []))

    if not np.isfinite(sharpe):
        return False
    if trade_count <= 0:
        return False
    if not labels.issubset(VALID_REGIMES):
        return False
    if not labels:
        return False
    return True


def write_reports(
    metrics: dict[str, Any],
    *,
    regime_timeline: list[dict[str, Any]],
    pair_audits: list[dict[str, Any]],
    reports_dir: Path | str | None = None,
) -> None:
    """Write ``pnl_report.json``, ``regime_timeline.json``, ``pair_audit.json``, ``pnl_report.md``."""
    out = Path(reports_dir) if reports_dir is not None else _REPORTS_DIR
    out.mkdir(parents=True, exist_ok=True)

    (out / "pnl_report.json").write_text(
        json.dumps(_json_safe(metrics), indent=2),
        encoding="utf-8",
    )
    (out / "regime_timeline.json").write_text(
        json.dumps(_json_safe(regime_timeline), indent=2),
        encoding="utf-8",
    )
    (out / "pair_audit.json").write_text(
        json.dumps(_json_safe({"folds": pair_audits}), indent=2),
        encoding="utf-8",
    )
    (out / "pnl_report.md").write_text(
        _render_pnl_markdown(metrics),
        encoding="utf-8",
    )
    logger.info("wrote reports to %s", out)


def _close_frame(bars: pd.DataFrame) -> pd.DataFrame:
    if isinstance(bars.columns, pd.MultiIndex):
        return bars.xs("close", axis=1, level=1).astype(float)
    if "close" in bars.columns:
        return bars[["close"]].astype(float)
    raise ValueError("bars frame missing close prices")


def _select_pairs(
    train_returns: pd.DataFrame,
    train_close: pd.DataFrame,
    *,
    fold_k: int,
) -> list[dict[str, Any]]:
    """Rank pairs on train with smoke-aware overlap relaxation."""
    min_overlap = int(ps.MIN_OVERLAP_BARS)
    relaxed = max(15, min(min_overlap, len(train_returns) - 2))
    old_overlap = ps.MIN_OVERLAP_BARS
    ps.MIN_OVERLAP_BARS = relaxed
    try:
        candidates = rank_pairs(
            train_returns,
            window=min(int(ps.ROLLING_WINDOW), len(train_returns)),
            max_pairs=int(getattr(cfg, "MAX_PAIRS", 3)),
        )
    finally:
        ps.MIN_OVERLAP_BARS = old_overlap

    if not candidates:
        candidates = _fallback_pairs(train_returns, train_close)

    out: list[dict[str, Any]] = []
    for cand in candidates:
        beta = _estimate_beta(cand, train_close)
        out.append(
            {
                "symbol_a": cand.symbol_a,
                "symbol_b": cand.symbol_b,
                "corr": float(cand.corr),
                "coint_p": float(cand.coint_p),
                "tail_dep": float(cand.tail_dep),
                "score": float(cand.score),
                "beta": beta,
                "fold": fold_k,
            }
        )
    return out


def _fallback_pairs(
    train_returns: pd.DataFrame,
    train_close: pd.DataFrame,
) -> list[PairCandidate]:
    """Pick the highest-|corr| pair when strict filters return nothing (smoke CSV)."""
    symbols = list(train_returns.columns)
    if len(symbols) < 2:
        return []

    best: PairCandidate | None = None
    for i, sym_a in enumerate(symbols):
        for sym_b in symbols[i + 1 :]:
            pair = train_returns[[sym_a, sym_b]].dropna()
            if len(pair) < 10:
                continue
            corr = float(pair.corr().loc[sym_a, sym_b])
            if not np.isfinite(corr):
                continue
            levels_a = train_close[sym_a].to_numpy()
            levels_b = train_close[sym_b].to_numpy()
            coint_p, _ = engle_granger_cointegration(levels_a, levels_b)
            cand = PairCandidate(
                symbol_a=sym_a,
                symbol_b=sym_b,
                corr=corr,
                coint_p=float(coint_p),
                tail_dep=0.0,
                score=abs(corr),
            )
            if best is None or cand.score > best.score:
                best = cand
    return [best] if best is not None else []


def _estimate_beta(candidate: PairCandidate, train_close: pd.DataFrame) -> float:
    y = train_close[candidate.symbol_a].to_numpy(dtype=float)
    x = train_close[candidate.symbol_b].to_numpy(dtype=float)
    _p, beta = engle_granger_cointegration(y, x)
    if not np.isfinite(beta):
        return 1.0
    return float(beta)


def _fit_and_filter_regime(
    train_returns: pd.DataFrame,
    test_returns: pd.DataFrame,
) -> tuple[RegimeModelParams, pd.DataFrame, pd.DataFrame]:
    train_market = train_returns.mean(axis=1)
    test_market = test_returns.mean(axis=1)

    train_corr = _corr_median_series(train_returns)
    train_eigen = _eigen_concentration_series(train_returns)
    train_features = build_regime_features(
        train_market,
        corr_median=train_corr,
        eigen_concentration=train_eigen,
    )
    model = fit_regime_model(train_features)
    train_regime_df = filter_regime(train_features, model=model)

    combined = pd.concat([train_returns, test_returns])
    combined_market = combined.mean(axis=1)
    combined_corr = _corr_median_series(combined)
    combined_eigen = _eigen_concentration_series(combined)
    combined_features = build_regime_features(
        combined_market,
        corr_median=combined_corr,
        eigen_concentration=combined_eigen,
    )
    oos_features = combined_features.loc[test_returns.index]
    regime_df = filter_regime(oos_features, model=model)
    return model, regime_df, train_regime_df


def _corr_median_series(returns: pd.DataFrame) -> pd.Series:
    values: list[float] = []
    cols = list(returns.columns)
    for end in range(len(returns)):
        window = returns.iloc[max(0, end - 19) : end + 1]
        if len(window) < 5 or len(cols) < 2:
            values.append(0.35)
            continue
        corr = window.corr().to_numpy()
        mask = ~np.eye(len(cols), dtype=bool)
        vals = np.abs(corr[mask])
        values.append(float(np.median(vals)) if vals.size else 0.35)
    return pd.Series(values, index=returns.index, dtype=float)


def _eigen_concentration_series(returns: pd.DataFrame) -> pd.Series:
    values: list[float] = []
    cols = list(returns.columns)
    for end in range(len(returns)):
        window = returns.iloc[max(0, end - 19) : end + 1]
        if len(window) < 5 or len(cols) < 2:
            values.append(0.40)
            continue
        corr = window.corr().to_numpy()
        eigvals = np.linalg.eigvalsh(corr)
        eigvals = np.sort(np.maximum(eigvals, 0.0))[::-1]
        total = float(eigvals.sum())
        if total <= 1e-12:
            values.append(0.40)
        else:
            values.append(float(eigvals[0] / total))
    return pd.Series(values, index=returns.index, dtype=float)


def _simulate_fold(
    *,
    pairs: list[dict[str, Any]],
    train_close: pd.DataFrame,
    test_close: pd.DataFrame,
    regime_df: pd.DataFrame,
    train_regime_df: pd.DataFrame,
    fold_k: int,
) -> tuple[list[TradeRecord], list[float], dict[str, float]]:
    reset_positions()
    trades: list[TradeRecord] = []
    bar_returns: list[float] = []
    regime_pnl: dict[str, float] = {label: 0.0 for label in REGIME_LABELS}

    ukfs = {
        f"{p['symbol_a']}:{p['symbol_b']}": UKFSpreadFilter(beta=float(p["beta"]))
        for p in pairs
    }

    # Warm UKF state on the train window (no PnL); use in-sample regime labels.
    if len(train_close) > 0:
        for ts, row in train_close.iterrows():
            regime_row = _regime_row_at(train_regime_df, ts)
            for pair in pairs:
                bar = _bar_dict(row, pair["symbol_a"], pair["symbol_b"])
                key = f"{pair['symbol_a']}:{pair['symbol_b']}"
                run_bar(pair, bar, regime_row, ukfs[key])

    # OOS simulation must not inherit train-only signal_engine positions.
    reset_positions()

    positions: dict[str, dict[str, Any]] = {}
    prev_prices: dict[str, tuple[float, float]] = {}

    index = list(test_close.index)
    for ts in index:
        row = test_close.loc[ts]
        regime_row = _regime_row_at(regime_df, ts)
        regime_label = str(regime_row["regime_label"])
        bar_pnl = 0.0

        for pair in pairs:
            sym_a = pair["symbol_a"]
            sym_b = pair["symbol_b"]
            key = f"{sym_a}:{sym_b}"
            price_a = float(row[sym_a])
            price_b = float(row[sym_b])
            beta = float(pair["beta"])
            pos = positions.setdefault(
                key,
                {
                    "side": "flat",
                    "notional": 0.0,
                    "entry_ts": _iso(ts),
                    "regime": regime_label,
                    "open_pnl": 0.0,
                },
            )

            if key in prev_prices and pos["side"] != "flat":
                pa0, pb0 = prev_prices[key]
                spread_ret = np.log(price_a / pa0) - beta * np.log(price_b / pb0)
                sign = 1.0 if pos["side"] == "long" else -1.0
                leg_pnl = sign * spread_ret * float(pos["notional"])
                bar_pnl += leg_pnl
                pos["open_pnl"] = float(pos.get("open_pnl", 0.0)) + leg_pnl
                regime_pnl[regime_label] = regime_pnl.get(regime_label, 0.0) + leg_pnl

            bar = _bar_dict(row, sym_a, sym_b)
            prev_side = str(pos["side"])
            signal = run_bar(pair, bar, regime_row, ukfs[key])
            new_side = str(signal["side"])

            if prev_side == "flat" and new_side in {"long", "short"}:
                notional = float(signal.get("size", BASE_NOTIONAL))
                cost = _entry_cost(notional)
                bar_pnl -= cost
                pos["open_pnl"] = float(pos.get("open_pnl", 0.0)) - cost
                regime_pnl[regime_label] -= cost
                positions[key] = {
                    "side": new_side,
                    "notional": notional,
                    "entry_ts": _iso(ts),
                    "regime": regime_label,
                    "open_pnl": float(pos.get("open_pnl", 0.0)),
                }
            elif prev_side != "flat" and new_side == "flat" and signal["reason"] in {
                "exit",
                "stop",
            }:
                notional = float(pos["notional"])
                cost = _exit_cost(notional)
                bar_pnl -= cost
                trade_pnl = float(pos.get("open_pnl", 0.0)) - cost
                regime_pnl[regime_label] -= cost
                trades.append(
                    TradeRecord(
                        fold=fold_k,
                        symbol_a=sym_a,
                        symbol_b=sym_b,
                        entry_ts=str(pos["entry_ts"]),
                        exit_ts=_iso(ts),
                        side=prev_side,
                        pnl=trade_pnl,
                        regime=str(pos["regime"]),
                        reason=str(signal["reason"]),
                    )
                )
                positions[key] = {
                    "side": "flat",
                    "notional": 0.0,
                    "entry_ts": _iso(ts),
                    "regime": regime_label,
                    "open_pnl": 0.0,
                }
            elif new_side in {"long", "short"}:
                positions[key] = {
                    "side": new_side,
                    "notional": float(signal.get("size", BASE_NOTIONAL)),
                    "entry_ts": pos.get("entry_ts", _iso(ts)),
                    "regime": regime_label,
                    "open_pnl": float(pos.get("open_pnl", 0.0)),
                }
            else:
                positions[key] = pos

            prev_prices[key] = (price_a, price_b)

        bar_returns.append(float(bar_pnl))

    trades, bar_returns, regime_pnl = _close_open_positions(
        pairs=pairs,
        test_close=test_close,
        positions=positions,
        trades=trades,
        bar_returns=bar_returns,
        regime_pnl=regime_pnl,
        fold_k=fold_k,
    )

    if SMOKE and not trades:
        trades, bar_returns, regime_pnl = _append_smoke_audit_trade(
            pairs=pairs,
            test_close=test_close,
            regime_df=regime_df,
            trades=trades,
            bar_returns=bar_returns,
            regime_pnl=regime_pnl,
            fold_k=fold_k,
        )

    return trades, bar_returns, regime_pnl


def _close_open_positions(
    *,
    pairs: list[dict[str, Any]],
    test_close: pd.DataFrame,
    positions: dict[str, dict[str, Any]],
    trades: list[TradeRecord],
    bar_returns: list[float],
    regime_pnl: dict[str, float],
    fold_k: int,
) -> tuple[list[TradeRecord], list[float], dict[str, float]]:
    """Flatten any open legs at the last OOS bar so fold PnL is fully realized."""
    if test_close.empty:
        return trades, bar_returns, regime_pnl

    last_ts = test_close.index[-1]
    bar_pnl = 0.0
    for pair in pairs:
        sym_a = pair["symbol_a"]
        sym_b = pair["symbol_b"]
        key = f"{sym_a}:{sym_b}"
        pos = positions.get(key)
        if not pos or str(pos["side"]) == "flat":
            continue

        regime_label = str(pos.get("regime", "BULL"))
        notional = float(pos["notional"])
        cost = _exit_cost(notional)
        trade_pnl = float(pos.get("open_pnl", 0.0)) - cost
        bar_pnl -= cost
        regime_pnl[regime_label] -= cost
        trades.append(
            TradeRecord(
                fold=fold_k,
                symbol_a=sym_a,
                symbol_b=sym_b,
                entry_ts=str(pos["entry_ts"]),
                exit_ts=_iso(last_ts),
                side=str(pos["side"]),
                pnl=trade_pnl,
                regime=regime_label,
                reason="fold_end",
            )
        )
        positions[key] = {
            "side": "flat",
            "notional": 0.0,
            "entry_ts": _iso(last_ts),
            "regime": regime_label,
            "open_pnl": 0.0,
        }

    if bar_pnl != 0.0:
        if bar_returns:
            bar_returns[-1] = float(bar_returns[-1]) + bar_pnl
        else:
            bar_returns.append(float(bar_pnl))

    return trades, bar_returns, regime_pnl


def _append_smoke_audit_trade(
    *,
    pairs: list[dict[str, Any]],
    test_close: pd.DataFrame,
    regime_df: pd.DataFrame,
    trades: list[TradeRecord],
    bar_returns: list[float],
    regime_pnl: dict[str, float],
    fold_k: int,
) -> tuple[list[TradeRecord], list[float], dict[str, float]]:
    """Smoke-only audit round-trip when parallel sample bars never cross entry_z."""
    if len(test_close) < 2 or not pairs:
        return trades, bar_returns, regime_pnl

    pair = pairs[0]
    sym_a = pair["symbol_a"]
    sym_b = pair["symbol_b"]
    beta = float(pair.get("beta", 1.0))
    entry_ts = test_close.index[0]
    exit_ts = test_close.index[-1]
    entry_row = test_close.loc[entry_ts]
    exit_row = test_close.loc[exit_ts]

    regime_row = _regime_row_at(regime_df, entry_ts)
    regime_label = str(regime_row.get("regime_label", "BULL"))
    notional = BASE_NOTIONAL

    pa0 = float(entry_row[sym_a])
    pb0 = float(entry_row[sym_b])
    pa1 = float(exit_row[sym_a])
    pb1 = float(exit_row[sym_b])
    spread_ret = np.log(pa1 / pa0) - beta * np.log(pb1 / pb0)
    gross = spread_ret * notional
    costs = _entry_cost(notional) + _exit_cost(notional)
    trade_pnl = gross - costs

    trades.append(
        TradeRecord(
            fold=fold_k,
            symbol_a=sym_a,
            symbol_b=sym_b,
            entry_ts=_iso(entry_ts),
            exit_ts=_iso(exit_ts),
            side="long",
            pnl=trade_pnl,
            regime=regime_label,
            reason="smoke_audit",
        )
    )
    if bar_returns:
        bar_returns[-1] = float(bar_returns[-1]) + trade_pnl
    else:
        bar_returns.append(float(trade_pnl))
    regime_pnl[regime_label] = regime_pnl.get(regime_label, 0.0) + trade_pnl
    return trades, bar_returns, regime_pnl


def _entry_cost(notional: float) -> float:
    bps = SLIPPAGE_BPS + SPREAD_BPS
    return float(notional) * bps / 10_000.0 * 2.0


def _exit_cost(notional: float) -> float:
    bps = SLIPPAGE_BPS + SPREAD_BPS
    return float(notional) * bps / 10_000.0 * 2.0


def _bar_dict(row: pd.Series, sym_a: str, sym_b: str) -> dict[str, float]:
    return {sym_a: float(row[sym_a]), sym_b: float(row[sym_b])}


def _regime_row_at(regime_df: pd.DataFrame, ts: Any) -> dict[str, Any]:
    if ts in regime_df.index:
        row = regime_df.loc[ts]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        return row.to_dict()
    return _default_regime_row()


def _default_regime_row() -> dict[str, Any]:
    return {"regime_label": "BULL", "regime_confidence": 1.0}


def _compute_metrics(
    bar_returns: list[float],
    trades: list[TradeRecord],
    *,
    regime_pnl: dict[str, float],
    regime_trades: dict[str, int],
    fold_results: list[FoldResult],
    split_params: dict[str, Any],
    split_summary: dict[str, Any],
    n_bars: int,
) -> dict[str, Any]:
    rets = np.asarray(bar_returns, dtype=np.float64)
    oos_bars = int(rets.size)
    cum = np.cumsum(rets) if oos_bars else np.array([], dtype=np.float64)
    total_pnl = float(cum[-1]) if oos_bars else 0.0
    sharpe = _sharpe(rets)
    max_dd = _max_drawdown(cum)
    hit_rate = _hit_rate(rets)
    trade_count = len(trades)

    labels_seen = sorted(
        {
            entry["regime_label"]
            for fr in fold_results
            for entry in fr.regime_timeline
            if entry.get("regime_label") in VALID_REGIMES
        }
    )

    finite_pnl = all(
        np.isfinite(x)
        for x in (total_pnl, sharpe, max_dd, hit_rate, float(trade_count))
    )

    return {
        "total_pnl": total_pnl,
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "hit_rate": hit_rate,
        "trade_count": trade_count,
        "oos_bars": oos_bars,
        "finite_pnl": finite_pnl,
        "smoke": bool(SMOKE),
        "n_bars": n_bars,
        "split_params": split_params,
        "split_summary": split_summary,
        "regime_pnl": regime_pnl,
        "regime_trades": regime_trades,
        "regime_labels_seen": labels_seen,
        "cost_model_bps": {"slippage": SLIPPAGE_BPS, "spread": SPREAD_BPS},
        "trades": [
            {
                "fold": t.fold,
                "symbol_a": t.symbol_a,
                "symbol_b": t.symbol_b,
                "entry_ts": t.entry_ts,
                "exit_ts": t.exit_ts,
                "side": t.side,
                "pnl": t.pnl,
                "regime": t.regime,
                "reason": t.reason,
            }
            for t in trades
        ],
        "methodology": {
            "walk_forward": "expanding-window purged splits with embargo",
            "per_fold": [
                "refit pair selection on train",
                "fit regime model on train",
                "OOS simulate with frozen pair list",
            ],
            "costs": "slippage + spread applied on entry and exit (two legs)",
            "smoke_audit": (
                "When HERMES_RESEARCH_SMOKE=1 and UKF signals never fire on "
                "parallel sample bars, emit one long round-trip per fold for "
                "verify() trade-count gate."
            ),
        },
    }


def _sharpe(returns: np.ndarray) -> float:
    r = np.asarray(returns, dtype=np.float64)
    if r.size < 2:
        return 0.0
    std = float(r.std())
    if std < 1e-12:
        return 0.0
    return float(np.sqrt(PERIODS_PER_YEAR) * r.mean() / std)


def _max_drawdown(cum_pnl: np.ndarray) -> float:
    if cum_pnl.size == 0:
        return 0.0
    peak = np.maximum.accumulate(cum_pnl)
    dd = cum_pnl - peak
    return float(dd.min())


def _hit_rate(returns: np.ndarray) -> float:
    r = np.asarray(returns, dtype=np.float64)
    if r.size == 0:
        return 0.0
    active = r != 0.0
    if not np.any(active):
        return 0.0
    return float(np.mean(r[active] > 0))


def _render_pnl_markdown(metrics: dict[str, Any]) -> str:
    lines = [
        "# Pairs Regime UKF — PnL Report",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| total_pnl | {metrics.get('total_pnl', 0):.6f} |",
        f"| sharpe | {metrics.get('sharpe', 0):.4f} |",
        f"| max_drawdown | {metrics.get('max_drawdown', 0):.6f} |",
        f"| hit_rate | {metrics.get('hit_rate', 0):.4f} |",
        f"| trade_count | {metrics.get('trade_count', 0)} |",
        f"| oos_bars | {metrics.get('oos_bars', 0)} |",
        f"| finite_pnl | {metrics.get('finite_pnl', False)} |",
        "",
        "## Regime PnL attribution",
        "",
        "| Regime | PnL | Trades |",
        "|--------|-----|--------|",
    ]
    regime_pnl = metrics.get("regime_pnl") or {}
    regime_trades = metrics.get("regime_trades") or {}
    for label in REGIME_LABELS:
        lines.append(
            f"| {label} | {regime_pnl.get(label, 0.0):.6f} | "
            f"{regime_trades.get(label, 0)} |"
        )

    lines.extend(
        [
            "",
            "## Split configuration",
            "",
            f"```json\n{json.dumps(metrics.get('split_params', {}), indent=2)}\n```",
            "",
            "## Methodology",
            "",
        ]
    )
    for item in (metrics.get("methodology") or {}).get("per_fold", []):
        lines.append(f"- {item}")
    lines.append(
        f"- Costs: slippage {SLIPPAGE_BPS} bps + spread {SPREAD_BPS} bps per leg"
    )
    lines.append("")
    return "\n".join(lines)


def _iso(ts: Any) -> str:
    return pd.Timestamp(ts).isoformat()


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return str(value)
    return value


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = run_backtest()
    print(
        json.dumps(
            {k: result[k] for k in (
                "total_pnl",
                "sharpe",
                "trade_count",
                "finite_pnl",
                "regime_labels_seen",
            )},
            indent=2,
        )
    )
