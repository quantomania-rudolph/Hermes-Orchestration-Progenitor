"""OOS-only backtest and PnL reporting for the LSTM + Optuna vault-equity pipeline (§11).

Runs purged expanding-window K-fold with Optuna tuning on train folds only,
retrains best models, concatenates outer-test predictions, and computes
portfolio metrics on OOS bars exclusively (invariant L5).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

import config
from data_loader import load_bars
from dataset import FoldScaler, build_sequences, minimum_rows
from nn_model import build_model, make_loaders, train_fold
from optuna_tuner import run_fold_tuning
from partial_forgetting import reset_lstm_hidden
from portfolio import PortfolioResult, simulate_portfolio
from purged_kfold import (
    EMBARGO_BARS,
    minimum_bars_for_splits,
    purged_kfold_splits,
    write_split_manifest,
)
from signals import FEATURE_COLS, build_feature_frame
from trading_loop import OOSFoldBatch, run_trading_loop_from_batches

logger = logging.getLogger(__name__)

PERIODS_PER_YEAR = 252 * 78
_ROOT = Path(__file__).resolve().parent
_REPORTS_DIR = _ROOT / "reports"
_MODELS_DIR = _ROOT / "models"

__all__ = [
    "PERIODS_PER_YEAR",
    "run_backtest",
    "verify",
    "write_reports",
]


def run_backtest(
    symbol: str = "AAPL",
    interval: str = "5min",
    *,
    reports_dir: Path | str | None = None,
    models_dir: Path | str | None = None,
    save_checkpoints: bool = True,
) -> dict[str, Any]:
    """
    Execute the full research pipeline and return OOS-only metrics.

    Adaptive split parameters are downscaled when the loaded sample is shorter
    than ``config`` defaults (mirror LR ``_walk_forward_params`` pattern).
    """
    reports_path = Path(reports_dir) if reports_dir is not None else _REPORTS_DIR
    models_path = Path(models_dir) if models_dir is not None else _MODELS_DIR
    reports_path.mkdir(parents=True, exist_ok=True)
    models_path.mkdir(parents=True, exist_ok=True)

    bars = load_bars(symbol=symbol, interval=interval)
    data_source = str(getattr(bars, "attrs", {}).get("data_source", ""))
    if not data_source:
        data_source = "auto (atoms→bars_bt→csv fallback chain)"

    feature_df = build_feature_frame(bars)
    n_bars = len(feature_df)
    split_params = adaptive_split_params(n_bars)

    timestamps = feature_df["bar_end_utc"].to_numpy()
    folds = purged_kfold_splits(
        timestamps,
        n_splits=split_params["n_splits"],
        min_train_bars=split_params["min_train_bars"],
        test_bars=split_params["test_bars"],
        lookback=split_params["lookback"],
        embargo_bars=EMBARGO_BARS,
    )

    manifest_path = reports_path / "split_manifest.json"
    split_manifest = write_split_manifest(
        manifest_path,
        timestamps,
        folds=folds,
        **split_params,
        embargo_bars=EMBARGO_BARS,
    )

    oos_batches: list[OOSFoldBatch] = []
    optuna_summaries: list[dict[str, Any]] = []
    fold_metrics: list[dict[str, Any]] = []
    optuna_best_params: dict[str, dict[str, Any]] = {}

    for fold_k, (train_idx, test_idx) in enumerate(folds):
        logger.info(
            "fold %d: train=%d test=%d bars",
            fold_k,
            train_idx.size,
            test_idx.size,
        )

        tuning = run_fold_tuning(
            train_idx,
            feature_df,
            fold_k,
            models_dir=models_path,
        )
        best_params = dict(tuning["best_params"])
        best_params["lookback"] = min(
            int(best_params.get("lookback", split_params["lookback"])),
            split_params["lookback"],
        )
        optuna_summaries.append(
            {
                "fold": fold_k,
                "best_val_loss": tuning.get("best_val_loss"),
                "n_trials": tuning.get("n_trials"),
                "method": tuning.get("method"),
                "best_params": best_params,
                "params_path": tuning.get("params_path"),
            }
        )
        optuna_best_params[str(fold_k)] = best_params

        batch = _retrain_and_predict_fold(
            train_idx,
            test_idx,
            feature_df,
            fold_k,
            best_params,
            models_dir=models_path if save_checkpoints else None,
        )
        oos_batches.append(batch)

        fold_metrics.append(
            {
                "fold": fold_k,
                "train_bars": int(train_idx.size),
                "test_bars": int(test_idx.size),
                "best_val_loss": _finite_float(tuning.get("best_val_loss")),
                "val_loss_method": tuning.get("method"),
            }
        )

    optuna_summary_path = reports_path / "optuna_summary.json"
    optuna_summary_path.write_text(
        json.dumps(
            {
                "smoke": config.SMOKE,
                "n_folds": len(folds),
                "folds": optuna_summaries,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    trading = run_trading_loop_from_batches(oos_batches)
    portfolio = simulate_portfolio(
        trading.strategy_returns,
        trading.positions,
        timestamps=trading.timestamps,
        fold_ids=trading.fold_ids,
    )

    metrics = _compute_metrics(
        portfolio,
        trading,
        optuna_best_params=optuna_best_params,
        fold_metrics=fold_metrics,
        symbol=symbol,
        interval=interval,
        data_source=data_source,
        adaptive_params=split_params,
        split_manifest_path=str(manifest_path),
        optuna_summary_path=str(optuna_summary_path),
        n_bars=n_bars,
    )
    write_reports(metrics, reports_dir=reports_path)
    return metrics


def adaptive_split_params(n_bars: int) -> dict[str, int]:
    """
    Downscale purged K-fold parameters until splits fit the available sample.

    Mirrors the LR ``_walk_forward_params`` adaptive pattern for short CSV runs.
    """
    n_splits = config.N_SPLITS
    min_train = config.MIN_TRAIN_BARS
    test_bars = config.TEST_BARS
    lookback = config.LOOKBACK

    for _ in range(32):
        need = minimum_bars_for_splits(
            n_splits,
            min_train_bars=min_train,
            test_bars=test_bars,
            embargo_bars=EMBARGO_BARS,
        )
        if n_bars >= need and n_bars >= minimum_rows(lookback=lookback):
            return {
                "n_splits": n_splits,
                "min_train_bars": min_train,
                "test_bars": test_bars,
                "lookback": lookback,
            }

        if test_bars > 10:
            test_bars = max(10, test_bars // 2)
        elif min_train > 40:
            min_train = max(40, min_train // 2)
        elif lookback > 15:
            lookback = max(15, lookback - 15)
        elif n_splits > 1:
            n_splits -= 1
        else:
            min_train = max(20, min_train // 2)
            if n_bars < min_train + test_bars + EMBARGO_BARS + 1:
                break

    raise ValueError(
        f"insufficient bars ({n_bars}) for purged K-fold even after adaptive "
        f"downscale (need >={minimum_rows()} feature rows)"
    )


def write_reports(
    metrics: dict[str, Any],
    *,
    reports_dir: Path | str | None = None,
) -> None:
    """Write ``pnl_report.json``, ``pnl_report.md``, and ``model_card.md``."""
    out = Path(reports_dir) if reports_dir is not None else _REPORTS_DIR
    out.mkdir(parents=True, exist_ok=True)

    json_path = out / "pnl_report.json"
    json_path.write_text(json.dumps(_json_safe(metrics), indent=2), encoding="utf-8")

    md_path = out / "pnl_report.md"
    md_path.write_text(_render_pnl_markdown(metrics), encoding="utf-8")

    card_path = out / "model_card.md"
    card_path.write_text(_render_model_card(metrics), encoding="utf-8")

    logger.info("wrote reports to %s", out)


def verify() -> bool:
    """Return True when OOS metrics are finite and non-empty."""
    metrics = run_backtest()
    return bool(metrics.get("finite_pnl")) and int(metrics.get("oos_bars", 0)) > 0


def _retrain_and_predict_fold(
    train_idx: np.ndarray,
    test_idx: np.ndarray,
    feature_df: pd.DataFrame,
    fold_k: int,
    best_params: dict[str, Any],
    *,
    models_dir: Path | None,
) -> OOSFoldBatch:
    lookback = int(best_params["lookback"])
    X, y_reg, _, ts_seq = build_sequences(
        feature_df,
        lookback=lookback,
        feature_cols=FEATURE_COLS,
    )

    train_seq = _bar_indices_to_seq_indices(
        train_idx,
        lookback=lookback,
        n_sequences=int(ts_seq.shape[0]),
    )
    test_seq = _bar_indices_to_seq_indices(
        test_idx,
        lookback=lookback,
        n_sequences=int(ts_seq.shape[0]),
    )
    if train_seq.size == 0 or test_seq.size == 0:
        raise ValueError(f"fold {fold_k}: empty train or test sequence indices")

    scaler = FoldScaler()
    scaler.fit(X[train_seq], feature_cols=FEATURE_COLS)

    X_train_full = scaler.transform(X[train_seq])
    y_train_full = y_reg[train_seq]

    batch_size = int(min(int(best_params["batch_size"]), len(train_seq)))
    batch_size = max(1, batch_size)
    # §8.4: retrain on full outer train; dummy val batch satisfies train_fold API.
    train_loader, val_loader = make_loaders(
        X_train_full,
        y_train_full,
        X_train_full[:1],
        y_train_full[:1],
        batch_size=batch_size,
    )

    model_kwargs = {
        k: best_params[k]
        for k in (
            "hidden_h1",
            "hidden_h2",
            "n_layers",
            "dropout_l1",
            "dropout_l2",
            "use_skip",
            "pfg_mode",
            "fold_reset",
        )
        if k in best_params
    }
    model_kwargs.setdefault("fold_reset", True)
    epochs = int(best_params.get("epochs", config.EPOCHS))
    loss_name = str(best_params.get("loss", "huber"))
    if loss_name == "bce":
        loss_name = "huber"
    model = build_model(X.shape[-1], **model_kwargs)
    train_fold(
        model,
        train_loader,
        val_loader,
        epochs=epochs,
        lr=float(best_params["lr"]),
        weight_decay=float(best_params["weight_decay"]),
        loss=loss_name,
        early_stop_patience=epochs + 1,
    )

    X_test = scaler.transform(X[test_seq])
    y_hat = _predict_sequences(model, X_test, batch_size=batch_size)

    if models_dir is not None:
        ckpt = models_dir / f"fold_{fold_k}_best.pt"
        torch.save(
            {
                "state_dict": model.state_dict(),
                "scaler": scaler.state_dict(),
                "hyperparams": best_params,
                "feature_cols": FEATURE_COLS,
                "lookback": lookback,
                "train_bar_end_range": [
                    str(feature_df.iloc[int(train_idx.min())]["bar_end_utc"]),
                    str(feature_df.iloc[int(train_idx.max())]["bar_end_utc"]),
                ],
            },
            ckpt,
        )

    aligned_bar_idx = test_seq.astype(np.int64) + (lookback - 1)

    return OOSFoldBatch(
        fold_id=fold_k,
        bar_idx=aligned_bar_idx,
        y_hat=y_hat,
        next_return=y_reg[test_seq],
        timestamps=ts_seq[test_seq],
        y_true=y_reg[test_seq],
    )


@torch.no_grad()
def _predict_sequences(
    model: torch.nn.Module,
    X: np.ndarray,
    *,
    batch_size: int = 64,
    device: torch.device | None = None,
) -> np.ndarray:
    dev = device or torch.device("cpu")
    model = model.to(dev)
    model.eval()
    reset_lstm_hidden(model)

    X_t = torch.as_tensor(X, dtype=torch.float32)
    parts: list[np.ndarray] = []
    for start in range(0, X_t.shape[0], batch_size):
        xb = X_t[start : start + batch_size].to(dev)
        preds = model(xb)
        parts.append(preds.detach().cpu().numpy())
    return np.concatenate(parts).astype(np.float64)


def _bar_indices_to_seq_indices(
    bar_idx: np.ndarray,
    *,
    lookback: int,
    n_sequences: int,
) -> np.ndarray:
    bars = np.asarray(bar_idx, dtype=np.int64)
    seq = bars - (lookback - 1)
    valid = (seq >= 0) & (seq < n_sequences)
    if not np.any(valid):
        return np.array([], dtype=np.int64)
    return np.sort(np.unique(seq[valid]))


def _compute_metrics(
    portfolio: PortfolioResult,
    trading: Any,
    *,
    optuna_best_params: dict[str, dict[str, Any]],
    fold_metrics: list[dict[str, Any]],
    symbol: str,
    interval: str,
    data_source: str,
    adaptive_params: dict[str, int],
    split_manifest_path: str,
    optuna_summary_path: str,
    n_bars: int,
) -> dict[str, Any]:
    rets = portfolio.strategy_return
    oos_bars = int(rets.shape[0])
    cum_nav = portfolio.cum_nav

    total_pnl = float(cum_nav[-1] - 1.0) if oos_bars > 0 else 0.0
    max_drawdown = float(np.min(portfolio.drawdown)) if oos_bars > 0 else 0.0
    sharpe = _sharpe(rets)
    trade_count = int(portfolio.bars_in_market)
    hit_rate = _hit_rate(portfolio)

    finite_pnl = all(
        np.isfinite(x)
        for x in (total_pnl, hit_rate, max_drawdown, sharpe, float(trade_count))
    )

    trade_log_summary = _trade_log_summary(portfolio)

    return {
        "total_pnl": total_pnl,
        "hit_rate": hit_rate,
        "max_drawdown": max_drawdown,
        "sharpe": sharpe,
        "trade_count": trade_count,
        "finite_pnl": finite_pnl,
        "oos_bars": oos_bars,
        "turnover": float(portfolio.turnover),
        "exposure_pct": float(portfolio.exposure_pct),
        "bars_in_market": int(portfolio.bars_in_market),
        "optuna_best_params": optuna_best_params,
        "fold_metrics": fold_metrics,
        "trade_log_summary": trade_log_summary,
        "trade_log": [
            {
                "fold_id": t.fold_id,
                "entry_bar_end_utc": _serialize_ts(t.entry_bar_end_utc),
                "exit_bar_end_utc": _serialize_ts(t.exit_bar_end_utc),
                "direction": int(t.direction),
                "pnl": float(t.pnl),
                "bars_held": int(t.bars_held),
            }
            for t in portfolio.trade_log
        ],
        "symbol": symbol,
        "interval": interval,
        "data_source": data_source,
        "smoke": config.SMOKE,
        "oos_only_attestation": True,
        "adaptive_params": adaptive_params,
        "feature_bars": n_bars,
        "split_manifest_path": split_manifest_path,
        "optuna_summary_path": optuna_summary_path,
        "periods_per_year": PERIODS_PER_YEAR,
        "methodology": {
            "leakage_controls": [
                "L1: features shifted one bar (bar_end <= t-1)",
                "L3: FoldScaler fit on train fold only",
                "L4: Optuna inner val on outer train only",
                "L5: PnL computed on concatenated OOS test folds only",
                "L7: LSTM hidden state reset at fold boundaries",
                "L8: purged expanding-window K-fold with embargo",
            ],
            "cost_model_bps": {"slippage": 1.0, "spread": 0.5},
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


def _hit_rate(portfolio: PortfolioResult) -> float:
    active = portfolio.position != 0
    if not np.any(active):
        return 0.0
    wins = portfolio.strategy_return[active] > 0
    return float(np.mean(wins))


def _trade_log_summary(portfolio: PortfolioResult) -> dict[str, Any]:
    trades = portfolio.trade_log
    if not trades:
        return {"count": 0, "win_rate": 0.0, "avg_pnl": 0.0}
    pnls = [float(t.pnl) for t in trades]
    return {
        "count": len(trades),
        "win_rate": float(np.mean([p > 0 for p in pnls])),
        "avg_pnl": float(np.mean(pnls)),
    }


def _render_pnl_markdown(metrics: dict[str, Any]) -> str:
    lines = [
        "# LSTM + Optuna Vault Equity — PnL Report",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| total_pnl | {metrics.get('total_pnl', 0):.6f} |",
        f"| hit_rate | {metrics.get('hit_rate', 0):.4f} |",
        f"| max_drawdown | {metrics.get('max_drawdown', 0):.6f} |",
        f"| sharpe | {metrics.get('sharpe', 0):.4f} |",
        f"| trade_count | {metrics.get('trade_count', 0)} |",
        f"| oos_bars | {metrics.get('oos_bars', 0)} |",
        f"| finite_pnl | {metrics.get('finite_pnl', False)} |",
        "",
        "## Run configuration",
        "",
        f"- Symbol: `{metrics.get('symbol', 'AAPL')}` / `{metrics.get('interval', '5min')}`",
        f"- Smoke mode: `{metrics.get('smoke', True)}`",
        f"- Feature bars: `{metrics.get('feature_bars', 0)}`",
        f"- Adaptive split params: `{metrics.get('adaptive_params', {})}`",
        "",
        "## OOS-only attestation",
        "",
        "PnL and trade statistics are computed **only** on outer purged K-fold test",
        "predictions. Optuna trials and inner validation never contribute to reported",
        "returns (invariant L5).",
        "",
        "## Fold metrics",
        "",
        "| Fold | Train bars | Test bars | Best val loss |",
        "|------|------------|-----------|---------------|",
    ]
    for fm in metrics.get("fold_metrics", []):
        lines.append(
            f"| {fm.get('fold')} | {fm.get('train_bars')} | {fm.get('test_bars')} | "
            f"{fm.get('best_val_loss')} |"
        )

    tls = metrics.get("trade_log_summary", {})
    lines.extend(
        [
            "",
            "## Trade log summary",
            "",
            f"- Round-trips: {tls.get('count', 0)}",
            f"- Win rate: {tls.get('win_rate', 0):.4f}",
            f"- Avg PnL per trade: {tls.get('avg_pnl', 0):.6f}",
            "",
            "## Artifacts",
            "",
            f"- Split manifest: `{metrics.get('split_manifest_path', 'reports/split_manifest.json')}`",
            f"- Optuna summary: `{metrics.get('optuna_summary_path', 'reports/optuna_summary.json')}`",
            "",
            "## Leakage controls",
            "",
        ]
    )
    for item in (metrics.get("methodology") or {}).get("leakage_controls", []):
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def _render_model_card(metrics: dict[str, Any]) -> str:
    adaptive = metrics.get("adaptive_params") or {}
    optuna_params = metrics.get("optuna_best_params") or {}
    lines = [
        "# Model Card — LSTM + Optuna Vault Equity Trader",
        "",
        "## 1. Data sources and cleaning lineage",
        "",
        "Loader priority: `alpha_atoms.atoms_5min_mkt` → `market_5min.equity_bars_bt`",
        "→ `sample_data/aapl_5min_sample.csv`. Upstream vault ingest applies RTH session",
        "filter, leakage guard on trailing bars, and `bar_end_utc` anchoring via atoms",
        "MVs and `*_bars_bt` views. This pipeline does not re-apply session filters.",
        "",
        f"- Data source used: `{metrics.get('data_source', 'sample/csv')}`",
        f"- Symbol / interval: `{metrics.get('symbol')}` / `{metrics.get('interval')}`",
        "",
        "## 2. Feature list and shift rules",
        "",
        "All features in `FEATURE_COLS` are shifted by one bar; labels use forward",
        "`next_return`. Signals: return lags, rolling vol, RSI(14), MACD trio,",
        "Bollinger %B, ATR/close, session progress.",
        "",
        "```",
        ", ".join(FEATURE_COLS),
        "```",
        "",
        "## 3. LSTM architecture (ASCII)",
        "",
        "```",
        "Input (batch, seq, features)",
        "    |",
        "    v",
        " LSTM Layer 1 + dropout",
        "    |",
        " [optional residual skip from x[:, -1, :]]",
        "    |",
        " LSTM Layer 2 + dropout (optional)",
        "    |",
        " Partial Forgetting Gate (PFG)",
        "    |",
        " Linear head -> next_return",
        "```",
        "",
        "## 4. Partial forgetting and fold_reset",
        "",
        "PFG blends LSTM hidden state with skip projection:",
        "`h_out = alpha * h_lstm + (1 - alpha) * h_skip`. During purged K-fold",
        "training `fold_reset=True` and hidden buffers are zeroed at fold boundaries",
        "(invariant L7).",
        "",
        "## 5. Purged K-fold + embargo",
        "",
        f"- n_splits: {adaptive.get('n_splits', config.N_SPLITS)}",
        f"- min_train_bars: {adaptive.get('min_train_bars', config.MIN_TRAIN_BARS)}",
        f"- test_bars: {adaptive.get('test_bars', config.TEST_BARS)}",
        f"- lookback: {adaptive.get('lookback', config.LOOKBACK)}",
        f"- embargo_bars: {EMBARGO_BARS}",
        "",
        "Expanding-window outer splits with purge zone",
        "`[test_start - max(lookback, embargo), test_end + embargo]`.",
        "",
        "## 6. Optuna search space and best params",
        "",
        "Search minimizes inner validation loss on the outer train fold only.",
        f"Trials per fold (smoke): {config.OPTUNA_TRIALS}.",
        "",
        "| Hyperparameter | Search range |",
        "|----------------|--------------|",
        "| lookback | 30–90 step 15 (clamped to adaptive split lookback) |",
        "| hidden_h1 | 32–128 step 32 |",
        "| hidden_h2 | 0–64 (0 disables layer 2) |",
        "| n_layers | {1, 2} |",
        "| dropout_l1 / l2 | 0.0–0.5 / 0.0–0.4 |",
        "| lr | 1e-4–5e-3 log |",
        "| weight_decay | 1e-6–1e-3 log |",
        "| batch_size | 32–128 |",
        f"| epochs | smoke 3–{config.EPOCHS} / full 10–{config.EPOCHS} |",
        "| use_skip | categorical |",
        "| pfg_mode | learned, scheduled |",
        "| loss | mse, huber, bce |",
        "",
    ]
    for fold_id, params in sorted(optuna_params.items(), key=lambda kv: int(kv[0])):
        lines.append(f"### Fold {fold_id} best params")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(_json_safe(params), indent=2))
        lines.append("```")
        lines.append("")

    lines.extend(
        [
            "## 7. OOS-only attestation",
            "",
            "Reported PnL (`total_pnl`, Sharpe, drawdown) uses **only** concatenated",
            "outer-test fold predictions after Optuna selection and full-train refit.",
            "No in-sample trial or inner-val path is included in trading simulation.",
            "",
            f"- oos_bars: {metrics.get('oos_bars', 0)}",
            f"- finite_pnl: {metrics.get('finite_pnl', False)}",
            f"- oos_only_attestation: {metrics.get('oos_only_attestation', True)}",
            "",
            "## 8. Comparison vs sklearn LR baseline",
            "",
            "Run `generated/vault_lr_strategy` on the same AAPL 5min sample for a",
            "linear-regression baseline; compare `total_pnl`, Sharpe, and max drawdown.",
            "",
        ]
    )
    return "\n".join(lines)


def _finite_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def _serialize_ts(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


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
    print(json.dumps({k: result[k] for k in (
        "total_pnl", "hit_rate", "max_drawdown", "sharpe",
        "trade_count", "finite_pnl", "oos_bars",
    )}, indent=2))
