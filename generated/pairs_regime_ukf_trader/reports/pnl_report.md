# Pairs Regime UKF — PnL Report

## Summary

| Metric | Value |
|--------|-------|
| total_pnl | -93.032024 |
| sharpe | -5.2915 |
| max_drawdown | -93.032024 |
| hit_rate | 0.0000 |
| trade_count | 2 |
| oos_bars | 20 |
| finite_pnl | True |

## Regime PnL attribution

| Regime | PnL | Trades |
|--------|-----|--------|
| BULL | 0.000000 | 0 |
| BEAR | 0.000000 | 0 |
| VOLATILE | -46.551462 | 1 |
| CRASH | -46.480562 | 1 |

## Split configuration

```json
{
  "n_splits": 2,
  "min_train_bars": 28,
  "test_bars": 10,
  "embargo_bars": 2,
  "purge_bars": 5
}
```

## Methodology

- refit pair selection on train
- fit regime model on train
- OOS simulate with frozen pair list
- Costs: slippage 1.0 bps + spread 0.5 bps per leg
