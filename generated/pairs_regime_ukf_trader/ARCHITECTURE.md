# Pairs Regime UKF Trader — Architecture

Research-only pipeline for regime-modulated pairs trading. No live order routing.

## Overview

1. **Pair discovery** — rolling Pearson/Spearman correlation, Engle–Granger cointegration, Gaussian/Clayton copula tail dependence.
2. **Regime model** — four-state anti-flicker Markov process on market features (minimum dwell, posterior smoothing).
3. **Spread dynamics** — Unscented Kalman Filter (UKF) on log-spread state `[level, velocity]`.
4. **Signal gating** — regime-dependent z-score thresholds and position caps.
5. **Validation** — purged walk-forward backtest with costs and audit artifacts.

## Four Markov Regimes

Each regime combines **detection rules** (features used by the Markov/HMM filter) with **trading parameters** (applied by the threshold modulator and signal engine).

### 1. BULL

**Detection**

| Feature | Rule |
|--------|------|
| Market return | Rolling aggregate return **> 0** |
| Realized volatility | Below **60th percentile** of in-sample history |
| Pairwise correlation stability | Median \|ρ\| drift **< 0.05** over **20** bars |
| Spread half-life | Stable (no material increase vs. trailing median) |

**Trading**

| Parameter | Value |
|-----------|-------|
| `entry_z` | **1.6** (tight) |
| `exit_z` | **0.4** |
| Position cap | **100%** of base notional |
| Copula tail gate | Not required |
| New entries | Allowed |

BULL is the most permissive regime: mean reversion is trusted, spreads are stable, and thresholds are contracted to capture smaller dislocations.

### 2. BEAR

**Detection**

| Feature | Rule |
|--------|------|
| Market drift | **Negative** (below-zero rolling return) |
| Realized volatility | **40th–80th percentile** band |
| Correlation | **Rising** but not spiking (moderate positive Δρ, below crash jump threshold) |

**Trading**

| Parameter | Value |
|-----------|-------|
| `entry_z` | **2.0** (moderate) |
| `exit_z` | **0.5** |
| Position cap | **70%** |
| Copula tail gate | Not required |
| New entries | Allowed |

BEAR widens thresholds slightly and reduces size as drift turns negative while volatility remains elevated but orderly.

### 3. VOLATILE

**Detection**

Triggered when **either**:

- Realized volatility **> 80th percentile**, **or**
- Correlation instability: eigenvalue concentration spike (first eigenvalue share of total variance jumps materially),

**and** there is **no** crash drawdown (5d market return ≥ −5%, no correlation breakdown jump).

**Trading**

| Parameter | Value |
|-----------|-------|
| `entry_z` | **2.8** (expanded) |
| `exit_z` | **0.8** |
| Position cap | **50%** |
| Copula tail gate | **Required** — entries need Gaussian/Clayton tail-dependence confirmation |
| New entries | Allowed when copula + regime confidence pass |

VOLATILE expands thresholds and halves risk; copula tail dependence filters false mean-reversion signals during unstable correlation structure.

### 4. CRASH

**Detection**

Triggered when **any** of:

- Rolling **5-day** market return **< −5%**
- VIX-proxy volatility **> 95th percentile**
- Correlation breakdown: average \|ρ\| jump **> 0.25** over **5** days

**Trading**

| Parameter | Value |
|-----------|-------|
| `entry_z` | **3.5** (widest) |
| `exit_z` | **1.2** |
| Position cap | **25%** |
| Copula tail gate | Not required (crash gate dominates) |
| New entries | **Blocked** if regime confidence **< 0.7** |

CRASH uses the widest thresholds and smallest cap; low-confidence crash states block new entries to avoid trading through structural breaks.

## Regime Ordering (Threshold Monotonicity)

Expected ordering for base parameters:

```
BULL (tightest) < BEAR < VOLATILE < CRASH (widest)
entry_z: 1.6 < 2.0 < 2.8 < 3.5
position_cap: 1.0 > 0.7 > 0.5 > 0.25
```

## Anti-Flicker Controls

Applied in `regime_markov.py` (later steps):

1. **Minimum dwell** — `MIN_REGIME_BARS = 5` before a committed switch.
2. **Posterior EMA smoothing** — `alpha = 0.15` on state probabilities.
3. **Switch commit threshold** — require `P(new_state) > 0.55` before changing label.

## Data Layer

`load_universe_bars()` loads daily-ish OHLCV for `config.UNIVERSE` (6 symbols in smoke):

1. PostgreSQL `market_daily.equity_bars`
2. Fallback: `sample_data/pairs_universe_bars.csv`

Returns a wide DataFrame with MultiIndex columns `(symbol, field)` indexed by `ts_utc`.

## Smoke Defaults (`HERMES_RESEARCH_SMOKE=1`)

| Setting | Value |
|---------|-------|
| `LIMIT_BARS` | 1200 |
| `UNIVERSE` | 6 symbols |
| `MAX_PAIRS` | 3 |
| `UKF_SMOKE` | 1 |
| `HERMES_USE_INTEL_XPU` | `auto` — use Intel Arc XPU when PyTorch XPU is available |

## Intel Arc / Core Ultra GPU Acceleration

Heavy linear algebra (rolling correlation matrices, batched level cumsums, future HMM/UKF batches) routes through `compute_device.py` and `gpu_kernels.py`:

| Module | Role |
|--------|------|
| `compute_device.py` | Resolves `torch.device`: Intel Arc XPU → CPU fallback |
| `gpu_kernels.py` | XPU Pearson correlation and batched cumsum for pair screens |

**Environment**

| Variable | Default | Meaning |
|----------|---------|---------|
| `HERMES_USE_INTEL_XPU` | `auto` | `1`/`auto` prefer Arc XPU; `0` force CPU |
| `HERMES_FORCE_CPU` | `0` | `1` disables XPU even if present |

On this workstation the detected device is **Intel Arc 140V (16 GB)** via PyTorch `torch.xpu`. Hermes brain / NoLlama LLM inference uses the same Arc stack under `scripts/run_intel_gpu/`.
