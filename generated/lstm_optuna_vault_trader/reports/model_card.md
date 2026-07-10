# Model Card — LSTM + Optuna Vault Equity Trader

## 1. Data sources and cleaning lineage

Loader priority: `alpha_atoms.atoms_5min_mkt` → `market_5min.equity_bars_bt`
→ `sample_data/aapl_5min_sample.csv`. Upstream vault ingest applies RTH session
filter, leakage guard on trailing bars, and `bar_end_utc` anchoring via atoms
MVs and `*_bars_bt` views. This pipeline does not re-apply session filters.

- Data source used: `auto (atoms→bars_bt→csv fallback chain)`
- Symbol / interval: `AAPL` / `5min`

## 2. Feature list and shift rules

All features in `FEATURE_COLS` are shifted by one bar; labels use forward
`next_return`. Signals: return lags, rolling vol, RSI(14), MACD trio,
Bollinger %B, ATR/close, session progress.

```
return_lag1, return_lag5, rolling_vol, rsi, macd, macd_signal, macd_hist, bb_pct_b, atr_norm, session_progress
```

## 3. LSTM architecture (ASCII)

```
Input (batch, seq, features)
    |
    v
 LSTM Layer 1 + dropout
    |
 [optional residual skip from x[:, -1, :]]
    |
 LSTM Layer 2 + dropout (optional)
    |
 Partial Forgetting Gate (PFG)
    |
 Linear head -> next_return
```

## 4. Partial forgetting and fold_reset

PFG blends LSTM hidden state with skip projection:
`h_out = alpha * h_lstm + (1 - alpha) * h_skip`. During purged K-fold
training `fold_reset=True` and hidden buffers are zeroed at fold boundaries
(invariant L7).

## 5. Purged K-fold + embargo

- n_splits: 2
- min_train_bars: 120
- test_bars: 40
- lookback: 30
- embargo_bars: 12

Expanding-window outer splits with purge zone
`[test_start - max(lookback, embargo), test_end + embargo]`.

## 6. Optuna search space and best params

Search minimizes inner validation loss on the outer train fold only.
Trials per fold (smoke): 3.

| Hyperparameter | Search range |
|----------------|--------------|
| lookback | 30–90 step 15 (clamped to adaptive split lookback) |
| hidden_h1 | 32–128 step 32 |
| hidden_h2 | 0–64 (0 disables layer 2) |
| n_layers | {1, 2} |
| dropout_l1 / l2 | 0.0–0.5 / 0.0–0.4 |
| lr | 1e-4–5e-3 log |
| weight_decay | 1e-6–1e-3 log |
| batch_size | 32–128 |
| epochs | smoke 3–5 / full 10–5 |
| use_skip | categorical |
| pfg_mode | learned, scheduled |
| loss | mse, huber, bce |

### Fold 0 best params

```json
{
  "lookback": 30,
  "hidden_h1": 64,
  "hidden_h2": 0,
  "n_layers": 1,
  "epochs": 5,
  "dropout_l1": 0.11569319232340314,
  "dropout_l2": 0.10994731168096124,
  "lr": 0.0010835794582109016,
  "weight_decay": 7.392538531872604e-05,
  "batch_size": 128,
  "use_skip": true,
  "pfg_mode": "scheduled",
  "loss": "huber",
  "fold_reset": true
}
```

### Fold 1 best params

```json
{
  "lookback": 30,
  "hidden_h1": 128,
  "hidden_h2": 0,
  "n_layers": 1,
  "epochs": 5,
  "dropout_l1": 0.26989657244414145,
  "dropout_l2": 0.021252603916542247,
  "lr": 0.000172564173327919,
  "weight_decay": 0.00016358262703585998,
  "batch_size": 128,
  "use_skip": true,
  "pfg_mode": "scheduled",
  "loss": "huber",
  "fold_reset": true
}
```

## 7. OOS-only attestation

Reported PnL (`total_pnl`, Sharpe, drawdown) uses **only** concatenated
outer-test fold predictions after Optuna selection and full-train refit.
No in-sample trial or inner-val path is included in trading simulation.

- oos_bars: 80
- finite_pnl: True
- oos_only_attestation: True

## 8. Comparison vs sklearn LR baseline

Run `generated/vault_lr_strategy` on the same AAPL 5min sample for a
linear-regression baseline; compare `total_pnl`, Sharpe, and max drawdown.
