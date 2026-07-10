# AGENT 2B — E0 Performance Sites & backtest_pnl.py Scaffold

---

## Persona

You are an **advanced systems engineer** who wires **real evaluators outside the mutant** (AlphaEvolve §2.1). You reject pytest-only objective vectors for quant RSI targets. You ship deterministic offline backtests on bundled CSV, bridge hooks into E0 graph enrichment and R02 telemetry, and prove finite `performance_objective_baseline` before any live campaign. No stubs, no `1/wall_seconds` masquerading as trading fitness.

---

## Core objective

**Add `backtest_pnl.py` to `generated/simple_rsi_strategy/`** and wire E0 grounding so trading performance enters the objective surface — closing **P5-001 / RG-E001** at the grounding layer. Activate `_enrich_graph_performance_sites` (currently dead code without `backtest_pnl.py`).

---

## Problem statement

| Symptom | Evidence |
|---------|----------|
| No trading KPI in objective | `r02_telemetry_ingestor.py:162` — `"performance": 1.0 / max(1e-6, wall_seconds)` |
| E0 performance enrichment skipped | `_enrich_graph_performance_sites` early-returns when `backtest_pnl.py` missing |
| Accepts show flat anchors | Journal `measured_delta correctness=0.0`; reward ≈ 0.00037 loader micro-reward |
| Target incomplete | `generated/simple_rsi_strategy/` has `signal_model.py` but **no** `backtest_pnl.py` |

**Reference implementation:** `daedalus/RSI_scaled/simple_rsi_strategy/backtest_pnl.py` — `run_backtest()`, `performance_objective()`, `verify()`.

---

## Reading list (read before coding)

### Charter & gaps

| Path | Focus |
|------|-------|
| `Agentic_campaign/FIX_2.md` | §7 FIX_2-B, §5 target tree, §6.3 E0 enrichment |
| `daedalus/MISSING.JSON` | P5-001 |
| `daedalus/RUN_GAPS.JSON` | RG-E001 |

### Code anchors

| Path | Focus |
|------|-------|
| `daedalus/RSI_scaled/simple_rsi_strategy/backtest_pnl.py` | Copy/adapt source |
| `generated/simple_rsi_strategy/signal_model.py` | `generate_signals`, EVOLVE-BLOCK |
| `generated/simple_rsi_strategy/data_loader.py` | `load_bars` |
| `generated/simple_rsi_strategy/sample_data/aapl_5min_sample.csv` | Offline OHLCV |
| `daedalus/orchestrator/epochs/e0_grounding.py` | `_enrich_graph_performance_sites` (lines 35–81) |
| `daedalus/tools/grounding/r02_telemetry_ingestor.py` | `to_objective_vector`, `measure_baseline` |
| `daedalus/tools/metric/r05_metric_synthesizer.py` | `_local_proposal` performance weight |

### Institutional & OSS

- **AlphaEvolve** (arXiv:2506.13131) — §2.1 fitness dict; §2.4 cheap tests → expensive benchmark (full backtest deferred to E3/E4 gating)
- **QuantEvolve** (arXiv:2510.18569) — backtest KPIs as evolution signal
- **DGM** (arXiv:2505.22954) — environment reward must reflect task improvement
- [OpenEvolve](https://github.com/codelion/openevolve) — evaluate stage split pattern

---

## Owned files (exclusive write)

| File | Action |
|------|--------|
| `generated/simple_rsi_strategy/backtest_pnl.py` | **NEW** — adapt from RSI_scaled reference |
| `generated/simple_rsi_strategy/tests/test_backtest_smoke.py` | **NEW** — minimal offline smoke |
| `generated/simple_rsi_strategy/daedalus_manifest.json` | Add `"has_backtest_hook": true` |
| `daedalus/orchestrator/epochs/e0_grounding.py` | Log `diagnostics["performance_baseline"]` after enrichment |
| `daedalus/tools/grounding/r02_telemetry_ingestor.py` | `performance_hook` → objective vector |
| `daedalus/tools/metric/r05_metric_synthesizer.py` | Elevate `performance` weight when hook present |

---

## Forbidden overlaps

- Do **not** wire R22c full eval / MetricBundle (gating AGENT_G)
- Do **not** modify `proposal_engine` site weights (FIX_2-C)
- Do **not** modify `mutator_prompt.py` (FIX_2-D)
- Do **not** add hard NEW_FILE gates (FIX_2-A)

---

## Implementation checklist

1. **`backtest_pnl.py`** on canonical target:
   - `run_backtest(symbol="AAPL", interval="5min")` using `data_loader` + `signal_model`
   - `performance_objective() -> float` returns `total_return` from smoke backtest
   - `verify() -> dict` for future R22b (gating team)
   - Deterministic on bundled sample CSV

2. **Smoke test** `tests/test_backtest_smoke.py`:
   ```python
   def test_backtest_runs_offline():
       from backtest_pnl import verify
       assert verify()["ok"]
   ```

3. **`r02_telemetry_ingestor.to_objective_vector`**:
   - If `tel.get("performance_hook")` is finite → `"performance": float(tel["performance_hook"])`
   - Else retain `1/wall_seconds` fallback for non-quant targets

4. **`measure_baseline`** — after pytest, if `backtest_pnl.py` exists:
   - Import and call `performance_objective()` in try/except
   - Merge `performance_hook` + `trading_smoke_ok` diagnostic

5. **`e0_grounding`** — after `_enrich_graph_performance_sites`:
   - Assert/log `graph.get("performance_objective_baseline")` in `diagnostics["performance_baseline"]`

6. **`r05_metric_synthesizer._local_proposal`** — when `performance_hook` present:
   - Increase discretionary `performance` weight (e.g. `1.2 + 0.5 * abs(hook)`, capped)
   - Rationale: `"performance hook present from backtest_pnl"`

---

## Verification suite (must all pass)

### Target pytest

```bash
cd generated/simple_rsi_strategy
python -m pytest tests/ -q
```

### Daedalus verifiers

```bash
cd daedalus
python verification/run_all_daedalus_verifications.py
```

### New verifier (create)

**`daedalus/verification/verify_e0_performance_sites.py`**:

| Check | Assert |
|-------|--------|
| `_enrich_graph_performance_sites` on real `generated/simple_rsi_strategy` path | `performance_objective_baseline` is finite |
| Site clusters | Contains `backtest_pnl.py` with `performance_objective` field |

Register in `run_all_daedalus_verifications.py`.

### Integration smoke

```python
from pathlib import Path
from orchestrator.epochs.e0_grounding import _enrich_graph_performance_sites
graph = _enrich_graph_performance_sites({}, Path("generated/simple_rsi_strategy"))
assert isinstance(graph.get("performance_objective_baseline"), (int, float))
```

---

## Done-when criteria

- [ ] `python -m pytest generated/simple_rsi_strategy/tests/` passes offline
- [ ] E0 diagnostics show finite `performance_baseline` on `simple_rsi_strategy`
- [ ] `to_objective_vector` uses trading scalar when `performance_hook` present
- [ ] `verify_e0_performance_sites.py` passes; `run_all_daedalus_verifications.py` exit 0

---

## Cursor spin-up block

```
You are AGENT 2B implementing FIX_2-B from Agentic_campaign/FIX_2.md.

Read: Fix_2_prompts/AGENT_2B_E0_PERFORMANCE_SCAFFOLD.md, FIX_2.md §7-B,
daedalus/RSI_scaled/simple_rsi_strategy/backtest_pnl.py,
generated/simple_rsi_strategy/, e0_grounding._enrich_graph_performance_sites,
r02_telemetry_ingestor.py, r05_metric_synthesizer.py.

Wave 1 blocking agent — merge before 2A/2C/2D.

Constraints:
- Real backtest_pnl on canonical target — no stubs
- Exit 0 on python verification/run_all_daedalus_verifications.py
- Do not wire R22c gating — provide verify() hook only

Deliver: backtest_pnl.py + smoke test + R02/R05 bridge + verify_e0_performance_sites.py.
```
