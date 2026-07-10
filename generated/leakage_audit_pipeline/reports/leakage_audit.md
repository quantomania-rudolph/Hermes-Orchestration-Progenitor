# Data Leakage Audit Report

## Summary

- Smoke mode: `True`
- Dataset tags: `clean_series, future_label_trap, scaler_trap, overlap_trap`
- Datasets audited: **4**
- Trap classes detected: **future_label, index_overlap, scaler_fit**
- Total findings: **6**
- Max severity: **1.0000**
- Mean severity: **0.8134**
- Aggregate score: **1.0000**
- All passed: **True**

## Per-dataset results

| Dataset | Trap class | Findings | Max severity | Passed |
|---------|------------|----------|--------------|--------|
| clean_series | clean | 0 | 0.0000 | True |
| future_label_trap | future_label | 1 | 1.0000 | True |
| scaler_trap | scaler_fit | 1 | 0.7500 | True |
| overlap_trap | index_overlap | 4 | 1.0000 | True |

## Findings detail

### clean_series (`clean`)

_No leakage findings._

### future_label_trap (`future_label`)

- **future_shift** (future_label): severity=1.0000 — feature 'return_lag1' shows future-information leakage (correlation=1.0000, shift_gap=0.9528 (lagged_correlation=0.0472), exact_match_fraction=1.0000)

### scaler_trap (`scaler_fit`)

- **scaler_leakage** (scaler_fit): severity=0.7500 — train and test feature stats are both near zero-mean/unit-variance, consistent with scaler fit on combined data

### overlap_trap (`index_overlap`)

- **index_overlap** (index_overlap): severity=0.1304 — train/test index overlap detected (3 shared indices)
- **purged_validator** (index_overlap): severity=1.0000 — train max index 93 must be strictly before test min index 8
- **purged_validator** (index_overlap): severity=1.0000 — train max timestamp must be strictly before test min timestamp
- **purged_validator** (index_overlap): severity=1.0000 — embargo gap -86 bars is less than required 2

