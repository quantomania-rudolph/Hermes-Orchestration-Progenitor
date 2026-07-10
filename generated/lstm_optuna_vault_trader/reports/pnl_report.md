# LSTM + Optuna Vault Equity — PnL Report

## Summary

| Metric | Value |
|--------|-------|
| total_pnl | 0.017574 |
| hit_rate | 0.6625 |
| max_drawdown | -0.016743 |
| sharpe | 46.4251 |
| trade_count | 80 |
| oos_bars | 80 |
| finite_pnl | True |

## Run configuration

- Symbol: `AAPL` / `5min`
- Smoke mode: `True`
- Feature bars: `524`
- Adaptive split params: `{'n_splits': 2, 'min_train_bars': 120, 'test_bars': 40, 'lookback': 30}`

## OOS-only attestation

PnL and trade statistics are computed **only** on outer purged K-fold test
predictions. Optuna trials and inner validation never contribute to reported
returns (invariant L5).

## Fold metrics

| Fold | Train bars | Test bars | Best val loss |
|------|------------|-----------|---------------|
| 0 | 90 | 40 | 7.408876263070852e-05 |
| 1 | 142 | 40 | 0.000657412747386843 |

## Trade log summary

- Round-trips: 5
- Win rate: 0.8000
- Avg PnL per trade: 0.003488

## Artifacts

- Split manifest: `C:\Users\Rudol\Desktop\Hermes_Orchestration\generated\lstm_optuna_vault_trader\reports\split_manifest.json`
- Optuna summary: `C:\Users\Rudol\Desktop\Hermes_Orchestration\generated\lstm_optuna_vault_trader\reports\optuna_summary.json`

## Leakage controls

- L1: features shifted one bar (bar_end <= t-1)
- L3: FoldScaler fit on train fold only
- L4: Optuna inner val on outer train only
- L5: PnL computed on concatenated OOS test folds only
- L7: LSTM hidden state reset at fold boundaries
- L8: purged expanding-window K-fold with embargo
