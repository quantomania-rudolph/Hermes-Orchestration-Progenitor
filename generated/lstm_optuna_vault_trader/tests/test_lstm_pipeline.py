"""Smoke tests for lstm_optuna_vault_trader (HERMES S009)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pytest

_PKG = Path(__file__).resolve().parents[1]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

os.environ.setdefault("HERMES_RESEARCH_SMOKE", "1")

from data_loader import load_bars
from purged_kfold import purged_kfold_splits
from signals import assert_no_leakage, build_feature_frame


def test_load_bars_sample():
    df = load_bars("AAPL", "5min")
    assert len(df) >= 100
    assert "bar_end_utc" in df.columns


def test_assert_no_leakage():
    bars = load_bars("AAPL", "5min")
    feat = build_feature_frame(bars)
    assert_no_leakage(feat)
    assert len(feat) > 50


def test_purged_kfold_ordering():
    bars = load_bars("AAPL", "5min")
    feat = build_feature_frame(bars)
    ts = feat["bar_end_utc"].to_numpy()
    folds = purged_kfold_splits(ts, n_splits=2, min_train_bars=80, test_bars=30)
    assert len(folds) >= 1
    for train_idx, test_idx in folds:
        assert train_idx.max() < test_idx.min()


def test_lstm_one_fold_cpu_smoke():
    torch = pytest.importorskip("torch")
    import config
    from dataset import FoldScaler, build_sequences
    from nn_model import build_model, make_loaders, train_fold

    bars = load_bars("AAPL", "5min")
    feat = build_feature_frame(bars)
    X, y_reg, y_cls, _ts = build_sequences(feat, lookback=config.LOOKBACK)
    assert len(X) > 20

    split = int(len(X) * 0.7)
    scaler = FoldScaler()
    X_train = scaler.fit_transform(X[:split])
    X_val = scaler.transform(X[split : split + 10])
    y_train = y_reg[:split]
    y_val = y_reg[split : split + 10]

    model = build_model(n_features=X.shape[2], hidden_h1=32, n_layers=1)
    train_loader, val_loader = make_loaders(
        X_train, y_train, X_val, y_val, batch_size=16
    )
    metrics = train_fold(model, train_loader, val_loader, epochs=2)
    assert np.isfinite(metrics["val_loss"])


def test_run_backtest_finite_oos():
    from backtest_pnl import run_backtest

    metrics = run_backtest()
    assert metrics["oos_bars"] > 0
    assert metrics["finite_pnl"] is True
