# AGENT 2C — Site Weight Policy Codification

---

## Persona

You are an **advanced systems engineer** who eliminates magic numbers from hot search paths. You codify site-weight policy as testable constants, align curriculum boosts with Voyager-style skill-library exploration (strategy-core clusters, not test files), and prove site distributions with Monte Carlo falsification. Regression-safe refactors only — identical default behavior unless charter specifies change.

---

## Core objective

**Extract `_resolve_site` weight multipliers into `site_weight_policy.py`**, add env-tunable constants, cap curriculum boost on test clusters, and emit `diag["site_weight_policy"]` for campaign observability. Close **P1-003** soft-weight half of RG-B001 with measurable site-selection bias toward RSI core files.

---

## Problem statement

Current state in `proposal_engine._resolve_site` (~176–218):

| Path pattern | Multiplier | Issue |
|--------------|------------|-------|
| `tests/` or `/test_` | ×0.12 | Inline magic number |
| `daedalus_quarantine/` + NEW_FILE + !core | ×0.08 | Soft only — insufficient alone |
| Strategy core files | ×1.4 | Not centralized |
| Curriculum boost | variable | May elevate underpopulated **test** clusters |

**Gap:** No single policy module, no test matrix, no Monte Carlo proof that strategy-core sites dominate when scaffold present. Live journal: `site_cluster=cluster::tests/test_heldout_loader.py` on ACCEPT.

---

## Reading list (read before coding)

### Charter & gaps

| Path | Focus |
|------|-------|
| `Agentic_campaign/FIX_2.md` | §7 FIX_2-C, §6.2 weight table, Appendix D site loop |
| `daedalus/MISSING.JSON` | P1-003 |
| `daedalus/RUN_GAPS.JSON` | RG-B001 site_cluster evidence |

### Code anchors

| Path | Focus |
|------|-------|
| `daedalus/search/proposal_engine.py` | `_resolve_site` (lines 176–218) |
| `daedalus/search/curriculum.py` | `curriculum_cluster_weights` |
| `daedalus/search/objective_intent.py` | `_RSI_CORE_FILES`, `has_strategy_core_scaffold` |
| `daedalus/config/daedalus_config.py` | Env var patterns |

### Institutional & OSS

- **QuantEvolve** (arXiv:2510.18569) — §4 feature map niches; site selection must map to behavioral descriptors
- **Voyager** (Wang et al.) — curriculum / underpopulated cluster bias toward **skills**, not test harness
- **AlphaEvolve** (arXiv:2506.13131) — problem surface defines valid edit sites
- [OpenEvolve](https://github.com/codelion/openevolve) — MAP-Elites / island patterns (reference)

---

## Owned files (exclusive write)

| File | Action |
|------|--------|
| `daedalus/search/site_weight_policy.py` | **NEW** — constants + `site_weight_multiplier()` |
| `daedalus/search/proposal_engine.py` | Refactor `_resolve_site` to call policy module only |
| `daedalus/search/curriculum.py` | Cap test-cluster boost at 1.0; allow strategy-core boost up to 1.8 |
| `daedalus/config/daedalus_config.py` | Optional env overrides |

---

## Forbidden overlaps

- Do **not** add hard operator gates (FIX_2-A owns `propose()` gate)
- Do **not** modify target tree files (FIX_2-B)
- Do **not** modify `mutator_prompt.py` (FIX_2-D)
- Coordinate with 2A: 2C merges **after** 2A on `proposal_engine.py`

---

## Implementation checklist

1. **Create `site_weight_policy.py`**:
   ```python
   TEST_SITE_FACTOR = 0.12
   QUARANTINE_NEWFILE_NO_CORE = 0.08
   QUARANTINE_DEFAULT = 0.35
   STRATEGY_CORE_FACTOR = 1.4
   STRATEGY_CORE_FILES = frozenset({"signal_model.py", "backtest_pnl.py", ...})

   def site_weight_multiplier(rel: str, *, operator: str, core_ready: bool) -> float: ...
   def is_test_site(rel: str) -> bool: ...
   def is_strategy_core(rel: str) -> bool: ...
   ```

2. **Refactor `_resolve_site`** — delegate to `site_weight_multiplier`; preserve identical defaults (regression-safe).

3. **Env overrides** (optional in `daedalus_config.py`):
   - `DAEDALUS_TEST_SITE_FACTOR` (default 0.12)
   - `DAEDALUS_STRATEGY_CORE_FACTOR` (default 1.4)
   - `DAEDALUS_QUARANTINE_NO_CORE_FACTOR` (default 0.08)

4. **`curriculum.py`** — in `curriculum_cluster_weights`:
   - Test sites: cap boost at `1.0`
   - Strategy-core files: allow `CURRICULUM_BOOST` up to `1.8`

5. **Cold-start bias** — when `cold=True` and `core_ready`, multiply strategy-core sites by additional `1.15`.

6. **Diagnostics** — `diag["site_weight_policy"] = {"core_ready", "candidates": [{file, weight}]}` top-5 weighted sites.

---

## Verification suite (must all pass)

### Primary gate

```bash
cd daedalus
python verification/run_all_daedalus_verifications.py
```

### New verifier — `verify_site_weight_policy.py`

| Test type | Assert |
|-----------|--------|
| Table-driven | `(rel, operator, core_ready) → multiplier` matches charter table |
| Edge cases | Unknown paths → factor 1.0; quarantine ×0.08 when NEW_FILE + !core |
| Monte Carlo | 1000× `_resolve_site` on fixture graph with strategy-core present → `P(test_site) < 0.05` |

### Extend `verify_curriculum.py`

- Test clusters never boosted above 1.0
- Strategy-core clusters can receive boost ≤ 1.8

### Regression

- Run full verification suite on non-quant target fixtures — no behavior change for unknown paths

---

## Done-when criteria

- [ ] All magic numbers moved to `site_weight_policy.py`
- [ ] Curriculum never boosts `tests/` above neutral
- [ ] Monte Carlo site distribution test passes
- [ ] No behavior regression on non-quant targets
- [ ] `run_all_daedalus_verifications.py` exit 0

---

## Cursor spin-up block

```
You are AGENT 2C implementing FIX_2-C from Agentic_campaign/FIX_2.md.

Read: Fix_2_prompts/AGENT_2C_SITE_WEIGHT_POLICY.md, FIX_2.md §7-C,
proposal_engine._resolve_site, curriculum.py, objective_intent.py.

Prerequisite: FIX_2-A merged (proposal_engine gate section stable).

Constraints:
- Refactor _resolve_site only — no operator hard gates
- Regression-safe defaults; extract constants to site_weight_policy.py
- Exit 0 on python verification/run_all_daedalus_verifications.py

Deliver: site_weight_policy.py + curriculum cap + verify_site_weight_policy.py + Monte Carlo test.
```
