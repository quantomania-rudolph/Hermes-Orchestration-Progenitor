#!/usr/bin/env python3
"""CLI entry for the pairs regime UKF research pipeline.

Usage::

    python run_pipeline.py           # respects HERMES_RESEARCH_SMOKE (default 1)
    python run_pipeline.py --smoke   # force smoke / CI parameters (<120s)
    python run_pipeline.py --full    # full research run
"""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib
import signal
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_PKG_ROOT = Path(__file__).resolve().parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

SMOKE_TIMEOUT_SEC = 120
_REPORTS_DIR = _PKG_ROOT / "reports"

__all__ = [
    "SMOKE_TIMEOUT_SEC",
    "LeakageError",
    "assert_no_leakage",
    "audit_leakage_folds",
    "corr_median_series",
    "eigen_concentration_series",
    "main",
    "run_pipeline",
    "run_with_timeout",
]


class LeakageError(AssertionError):
    """Raised when a feature frame or fold violates anti-leakage invariants."""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run regime-modulated pairs UKF walk-forward backtest.",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="force HERMES_RESEARCH_SMOKE=1 and enforce 120s runtime budget",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="force HERMES_RESEARCH_SMOKE=0 (full research parameters)",
    )
    return parser.parse_args()


def _reload_config_dependent_modules() -> None:
    """Reload modules that snapshot config constants at import time."""
    for mod_name in (
        "config",
        "purged_splits",
        "pair_selection",
        "regime_markov",
        "backtest_pnl",
    ):
        mod = importlib.import_module(mod_name)
        importlib.reload(mod)


def _write_device_report(reports_dir: Path) -> Path:
    from compute_device import device_report

    reports_dir.mkdir(parents=True, exist_ok=True)
    out = reports_dir / "device_report.json"
    out.write_text(json.dumps(device_report(), indent=2), encoding="utf-8")
    return out


def _close_frame(bars: pd.DataFrame) -> pd.DataFrame:
    if isinstance(bars.columns, pd.MultiIndex):
        return bars.xs("close", axis=1, level=1).astype(float)
    raise ValueError("bars frame missing MultiIndex close columns")


def _corr_median_series(returns: pd.DataFrame) -> pd.Series:
    """Rolling cross-sectional |corr| median (mirrors backtest feature path)."""
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
    """Rolling leading eigenvalue share of the correlation matrix."""
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


corr_median_series = _corr_median_series
eigen_concentration_series = _eigen_concentration_series


def leakage_safe_regime_features(
    market_returns: pd.Series,
    *,
    corr_median: pd.Series | None = None,
    eigen_concentration: pd.Series | None = None,
) -> pd.DataFrame:
    """Build regime features with a mandatory one-bar shift (L1 guard)."""
    from regime_markov import build_regime_features

    raw = build_regime_features(
        market_returns,
        corr_median=corr_median,
        eigen_concentration=eigen_concentration,
    )
    return raw.shift(1)


def assert_features_shifted_one_bar(
    features_df: pd.DataFrame,
    market_returns: pd.Series,
    *,
    corr_median: pd.Series | None = None,
    eigen_concentration: pd.Series | None = None,
) -> None:
    """Fail unless every feature column is exactly raw.shift(1)."""
    if features_df.empty:
        raise LeakageError("feature frame is empty after shift")

    from regime_markov import FEATURE_COLS, build_regime_features

    missing = [col for col in FEATURE_COLS if col not in features_df.columns]
    if missing:
        raise LeakageError(f"feature frame missing required columns: {missing}")

    ret = market_returns.astype(float)
    raw = build_regime_features(
        ret,
        corr_median=corr_median,
        eigen_concentration=eigen_concentration,
    )
    expected = raw.shift(1).reindex(features_df.index)

    if not features_df.columns.equals(expected.columns):
        raise LeakageError(
            f"feature columns {list(features_df.columns)} != expected {list(expected.columns)}"
        )

    if len(features_df) > 0 and not features_df.iloc[0].isna().all():
        raise LeakageError("first bar must be NaN after mandatory shift(1)")

    for col in FEATURE_COLS:
        got = features_df[col].astype(float)
        exp = expected[col].astype(float)
        mask = got.notna() & exp.notna()
        if not mask.any():
            raise LeakageError(f"{col} has no overlapping non-NaN values after shift(1)")

        if not np.allclose(got[mask].to_numpy(), exp[mask].to_numpy(), rtol=1e-9, atol=1e-12):
            raise LeakageError(f"{col} is not exactly shift(1) of raw regime features")


def _same_pair_candidates(
    left: list[Any],
    right: list[Any],
    *,
    tol: float = 1e-9,
) -> bool:
    if len(left) != len(right):
        return False
    for a, b in zip(left, right):
        if (a.symbol_a, a.symbol_b) != (b.symbol_a, b.symbol_b):
            return False
        if abs(float(a.score) - float(b.score)) > tol:
            return False
    return True


def _rank_pairs_train_window(train_returns: pd.DataFrame) -> list[Any]:
    """Rank pairs on a train slice with smoke-aware overlap relaxation."""
    import pair_selection as ps
    from pair_selection import rank_pairs

    min_overlap = int(ps.MIN_OVERLAP_BARS)
    relaxed = max(15, min(min_overlap, len(train_returns) - 2))
    old_overlap = ps.MIN_OVERLAP_BARS
    ps.MIN_OVERLAP_BARS = relaxed
    try:
        return rank_pairs(
            train_returns,
            window=min(int(ps.ROLLING_WINDOW), len(train_returns)),
        )
    finally:
        ps.MIN_OVERLAP_BARS = old_overlap


def assert_pair_scores_train_only(
    train_returns: pd.DataFrame,
    test_returns: pd.DataFrame,
) -> None:
    """Ensure pair ranking on train is invariant to perturbed OOS rows."""
    import pair_selection as ps
    from pair_selection import rank_pairs

    min_overlap = int(ps.MIN_OVERLAP_BARS)
    relaxed = max(15, min(min_overlap, len(train_returns) - 2))
    window = min(int(ps.ROLLING_WINDOW), len(train_returns))
    baseline = _rank_pairs_train_window(train_returns)
    poisoned_test = test_returns.astype(float) * 100.0 + 50.0
    combined = pd.concat([train_returns, poisoned_test])

    old_overlap = ps.MIN_OVERLAP_BARS
    ps.MIN_OVERLAP_BARS = relaxed
    try:
        by_index = rank_pairs(combined.loc[train_returns.index], window=window)
        by_position = rank_pairs(combined.iloc[: len(train_returns)], window=window)
    finally:
        ps.MIN_OVERLAP_BARS = old_overlap

    if not baseline:
        raise LeakageError(
            "pair ranking returned no candidates on train window "
            f"(bars={len(train_returns)}, overlap={relaxed})"
        )

    if not _same_pair_candidates(baseline, by_index):
        raise LeakageError("pair scores change when OOS rows are perturbed (index slice)")
    if not _same_pair_candidates(baseline, by_position):
        raise LeakageError("pair scores change when OOS rows are perturbed (positional slice)")


def audit_leakage_folds(
    log_returns: pd.DataFrame,
    folds: list[tuple[np.ndarray, np.ndarray]],
) -> dict[str, Any]:
    """Run purged-split and per-fold leakage checks; return audit manifest."""
    from purged_splits import assert_purge_valid

    entries: list[dict[str, Any]] = []
    for fold_k, (train_idx, test_idx) in enumerate(folds):
        assert_purge_valid(train_idx, test_idx)
        train_returns = log_returns.iloc[train_idx]
        test_returns = log_returns.iloc[test_idx]
        assert_pair_scores_train_only(train_returns, test_returns)

        market = train_returns.mean(axis=1)
        train_corr = _corr_median_series(train_returns)
        train_eigen = _eigen_concentration_series(train_returns)
        shifted = leakage_safe_regime_features(
            market,
            corr_median=train_corr,
            eigen_concentration=train_eigen,
        )
        assert_features_shifted_one_bar(
            shifted,
            market,
            corr_median=train_corr,
            eigen_concentration=train_eigen,
        )
        train_pairs = _rank_pairs_train_window(train_returns)

        entries.append(
            {
                "fold": fold_k,
                "train_count": int(train_idx.size),
                "test_count": int(test_idx.size),
                "train_max": int(train_idx.max()),
                "test_min": int(test_idx.min()),
                "purge_gap": int(test_idx.min() - train_idx.max() - 1),
                "pair_count_train": len(train_pairs),
            }
        )

    return {
        "folds_audited": len(entries),
        "feature_shift_bars": 1,
        "pair_scores_train_only": True,
        "folds": entries,
    }


def assert_no_leakage(
    *,
    bars: pd.DataFrame | None = None,
    log_returns: pd.DataFrame | None = None,
) -> None:
    """Assert L1 feature shift and no future pair scores in train folds."""
    from data_loader import load_universe_bars
    from purged_splits import adaptive_split_params, expanding_purged_splits

    if log_returns is None:
        if bars is None:
            bars = load_universe_bars()
        close = _close_frame(bars)
        log_returns = (
            np.log(close / close.shift(1))
            .replace([np.inf, -np.inf], np.nan)
            .fillna(0.0)
        )

    split_params = adaptive_split_params(len(log_returns))
    folds = expanding_purged_splits(len(log_returns), **split_params)
    audit_leakage_folds(log_returns, folds)


def run_pipeline(*, smoke: bool | None = None) -> dict[str, Any]:
    """Execute backtest, write reports, and return metrics summary."""
    if smoke is True:
        os.environ["HERMES_RESEARCH_SMOKE"] = "1"
    elif smoke is False:
        os.environ["HERMES_RESEARCH_SMOKE"] = "0"

    _reload_config_dependent_modules()

    from backtest_pnl import run_backtest

    metrics = run_backtest(reports_dir=_REPORTS_DIR)
    _write_device_report(_REPORTS_DIR)
    return metrics


def run_with_timeout(fn: Any, timeout_sec: float) -> dict[str, Any]:
    """Run *fn* in-process; raise ``TimeoutError`` when *timeout_sec* elapses."""
    if hasattr(signal, "SIGALRM"):

        def _on_alarm(_signum: int, _frame: Any) -> None:
            raise TimeoutError(f"exceeded {timeout_sec}s budget")

        previous = signal.signal(signal.SIGALRM, _on_alarm)
        signal.alarm(max(1, int(timeout_sec)))
        try:
            return fn()
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(fn).result(timeout=timeout_sec)


def main() -> int:
    args = _parse_args()
    if args.smoke and args.full:
        print("error: --smoke and --full are mutually exclusive", file=sys.stderr)
        return 2

    if args.smoke:
        smoke_mode = True
        os.environ["HERMES_RESEARCH_SMOKE"] = "1"
    elif args.full:
        smoke_mode = False
        os.environ["HERMES_RESEARCH_SMOKE"] = "0"
    else:
        smoke_mode = os.getenv("HERMES_RESEARCH_SMOKE", "1") == "1"

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        if smoke_mode:
            metrics = run_with_timeout(lambda: run_pipeline(smoke=True), SMOKE_TIMEOUT_SEC)
        else:
            metrics = run_pipeline(smoke=False)
    except (TimeoutError, concurrent.futures.TimeoutError):
        print(
            f"error: smoke pipeline exceeded {SMOKE_TIMEOUT_SEC}s budget",
            file=sys.stderr,
        )
        return 1

    summary = {
        "total_pnl": metrics.get("total_pnl"),
        "sharpe": metrics.get("sharpe"),
        "trade_count": metrics.get("trade_count"),
        "finite_pnl": metrics.get("finite_pnl"),
        "oos_bars": metrics.get("oos_bars"),
        "regime_labels_seen": metrics.get("regime_labels_seen"),
        "smoke": metrics.get("smoke"),
        "device_report": str(_REPORTS_DIR / "device_report.json"),
    }
    print(json.dumps(summary, indent=2))

    ok = (
        bool(metrics.get("finite_pnl"))
        and int(metrics.get("oos_bars", 0)) > 0
        and int(metrics.get("trade_count", 0)) > 0
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
