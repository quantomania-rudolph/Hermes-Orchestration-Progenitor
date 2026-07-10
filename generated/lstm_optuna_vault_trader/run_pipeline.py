#!/usr/bin/env python3
"""CLI entry for the LSTM + Optuna vault-equity research pipeline (§21.5).

Usage::

    python run_pipeline.py           # respects HERMES_RESEARCH_SMOKE (default 1)
    python run_pipeline.py --smoke   # force smoke / CI parameters
    python run_pipeline.py --full    # full research run (50k bars, 20 Optuna trials)
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run LSTM+Optuna vault-equity backtest and write reports.",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="force HERMES_RESEARCH_SMOKE=1 (2k bars, 2 folds, 3 Optuna trials)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="force HERMES_RESEARCH_SMOKE=0 (full research parameters)",
    )
    parser.add_argument(
        "--symbol",
        default="AAPL",
        help="equity symbol (default: AAPL)",
    )
    parser.add_argument(
        "--interval",
        default="5min",
        choices=("5min", "15min"),
        help="bar interval (default: 5min)",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.smoke and args.full:
        print("error: --smoke and --full are mutually exclusive", file=sys.stderr)
        return 2
    if args.smoke:
        os.environ["HERMES_RESEARCH_SMOKE"] = "1"
    elif args.full:
        os.environ["HERMES_RESEARCH_SMOKE"] = "0"

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    import config

    importlib.reload(config)

    # Modules that snapshot config at import must reload after --smoke/--full.
    for mod_name in (
        "signals",
        "dataset",
        "purged_kfold",
        "nn_model",
        "optuna_tuner",
        "backtest_pnl",
    ):
        mod = importlib.import_module(mod_name)
        importlib.reload(mod)

    from backtest_pnl import run_backtest

    metrics = run_backtest(symbol=args.symbol, interval=args.interval)

    summary = {
        "total_pnl": metrics.get("total_pnl"),
        "hit_rate": metrics.get("hit_rate"),
        "max_drawdown": metrics.get("max_drawdown"),
        "sharpe": metrics.get("sharpe"),
        "trade_count": metrics.get("trade_count"),
        "finite_pnl": metrics.get("finite_pnl"),
        "oos_bars": metrics.get("oos_bars"),
        "split_manifest": metrics.get("split_manifest_path"),
        "optuna_summary": metrics.get("optuna_summary_path"),
    }
    print(json.dumps(summary, indent=2))
    return 0 if metrics.get("finite_pnl") and int(metrics.get("oos_bars", 0)) > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
