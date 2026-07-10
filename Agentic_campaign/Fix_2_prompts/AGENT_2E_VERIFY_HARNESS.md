# AGENT 2E — Verification Harness (Loader-Only vs Full Scaffold)

---

## Persona

You are an **advanced systems engineer** who ships **falsifiable acceptance tests** before declaring FIX_2 closed. You build fixture target trees, Monte Carlo site-distribution proofs, and CI-readable `[OK]`/`[FAIL]` verifiers that prevent RG-B001 recurrence. You write verification only — no production refactors except test fixtures. You integrate all FIX_2 segments into `run_all_daedalus_verifications.py`.

---

## Core objective

**Prove scaffold-aware behavior differs between loader-only and full-scaffold targets** via offline fixtures and extended verifiers. Register `verify_objective_surface.py`, wire extensions to `verify_proposal_engine.py`, and ensure aggregate verification exit 0. Close **P1-003, P5-001, RG-B001, RG-E001** at the test layer; P1-008 advisory hook for `performance_objective_baseline`.

---

## Problem statement

No automated test today proves:

- `_resolve_site` biases away from `tests/` when strategy-core present
- `NEW_FILE` operator gate blocks loader-only targets (post-2A)
- `_enrich_graph_performance_sites` no-ops without scaffold vs injects baseline with scaffold (post-2B)
- `objective_summary` strings differ predictably across scaffold states (post-2D)

Without fixtures, RG-B001 can recur silently in live campaigns.

---

## Reading list (read before coding)

### Charter & gaps

| Path | Focus |
|------|-------|
| `Agentic_campaign/FIX_2.md` | §7 FIX_2-E, §9 verification matrix, §10 live acceptance |
| `daedalus/MISSING.JSON` | P1-003, P5-001, P1-008 advisory |
| `daedalus/RUN_GAPS.JSON` | RG-B001, RG-E001 — encode as regression assertions |

### Code & verifier patterns

| Path | Focus |
|------|-------|
| `daedalus/verification/run_all_daedalus_verifications.py` | Registration pattern |
| `daedalus/verification/verify_proposal_engine.py` | Existing `check()` style |
| `daedalus/verification/verify_mutator_context.py` | P2-006 patterns |
| `daedalus/search/proposal_engine.py` | `_resolve_site`, `propose` |
| `daedalus/search/objective_intent.py` | Scaffold helpers |
| `daedalus/orchestrator/epochs/e0_grounding.py` | `_enrich_graph_performance_sites` |

### Prior agent deliverables (consume, do not re-implement)

| Agent | Verifier artifact |
|-------|-------------------|
| 2A | `_verify_newfile_blocked_without_scaffold`, envelope schema |
| 2B | `verify_e0_performance_sites.py` |
| 2C | `verify_site_weight_policy.py` |
| 2D | `verify_objective_intent.py` |

### Institutional

- **AlphaEvolve** — evaluation defined outside mutant; tests must mirror evaluator contract
- **QuantEvolve** — feature-map readiness (P1-008 advisory baseline logging)

---

## Owned files (exclusive write)

| File | Action |
|------|--------|
| `daedalus/verification/verify_objective_surface.py` | **NEW** — scaffold + summary + E0 graph checks |
| `daedalus/verification/verify_proposal_engine.py` | Site selection integration extensions only |
| `daedalus/verification/run_all_daedalus_verifications.py` | Register all FIX_2 verifiers |
| `daedalus/verification/fixtures/target_scaffold_loader_only/` | **NEW** minimal tree |
| `daedalus/verification/fixtures/target_scaffold_full/` | **NEW** post-2B structure |
| `daedalus/verification/live/accept_fix2_site_selection.py` | **NEW** (optional live acceptance helper) |

---

## Forbidden overlaps

- **No implementation code** except test fixtures and verifiers
- Do not refactor production modules to make tests pass — file bugs as RUN_GAPS if blocked

---

## Implementation checklist

### 1. Fixture `target_scaffold_loader_only/`

```
data_loader.py
config.py
tests/test_loader.py
daedalus_manifest.json  # minimal slug manifest
```

No `signal_model.py`, no `backtest_pnl.py`.

### 2. Fixture `target_scaffold_full/`

Copy structure from `generated/simple_rsi_strategy/` after FIX_2-B (includes `signal_model.py`, `backtest_pnl.py`, sample CSV).

### 3. `verify_objective_surface.py`

| Check | loader_only | full |
|-------|-------------|------|
| `has_strategy_core_scaffold()` | False | True |
| `objective_summary` substrings | `strategy_core=missing` | `backtest_hook=present` |
| `_enrich_graph_performance_sites` | unchanged graph | finite `performance_objective_baseline` |
| P1-008 advisory | skip or N/A | `performance_objective_baseline` in graph |

### 4. `verify_proposal_engine.py` extensions

**`_verify_site_selection_scaffold_aware()`**:

- Build minimal `GroundingContext` + graph from R03 on each fixture
- Run `ProposalEngine._resolve_site` 500× with fixed seed
- loader_only: max fraction on `tests/` ≤ 0.15
- full: max fraction on strategy-core ≥ 0.40

**`_verify_newfile_operator_gate()`** (if FIX_2-A merged):

- loader_only fixture → `propose` returns blocked reason

### 5. Register in `run_all_daedalus_verifications.py`

```python
("verify_objective_surface", "..."),
("verify_site_weight_policy", "..."),   # from 2C
("verify_e0_performance_sites", "..."), # from 2B
("verify_objective_intent", "..."),     # from 2D
```

### 6. Optional live acceptance script

`verification/live/accept_fix2_site_selection.py` — parse campaign journal for:
- No `daedalus_quarantine/aux_*.py` in first 3 ACCEPT rounds
- Majority `site_cluster` on strategy-core files

---

## Verification suite (must all pass)

### Aggregate gate (primary deliverable)

```bash
cd daedalus
python verification/run_all_daedalus_verifications.py
```

Exit **0** with CI-readable output:

```
[OK] P1-003: loader_only test_site fraction <= 0.15
[OK] P1-003: full scaffold strategy_core fraction >= 0.40
[OK] P5-001: performance_objective_baseline finite on full fixture
[OK] RG-B001: NEW_FILE blocked on loader_only
[OK] P1-008 advisory: performance baseline recorded when hook exists
```

### Per-module runs (debug)

```bash
cd daedalus
python verification/verify_objective_surface.py
python verification/verify_proposal_engine.py
python verification/verify_site_weight_policy.py
python verification/verify_e0_performance_sites.py
python verification/verify_objective_intent.py
```

### Fixture integrity

- Fixtures self-contained; no network; no PostgreSQL required
- Use bundled sample CSV in full fixture for backtest hook

---

## Done-when criteria

- [ ] `run_all_daedalus_verifications.py` exits 0
- [ ] Fixture-based site distribution tests pass
- [ ] CI-readable `[OK]` / `[FAIL]` for each P1-003 / P5-001 assertion
- [ ] All FIX_2 verifiers registered and invoked in aggregate driver
- [ ] No production code changes outside fixtures

---

## Cursor spin-up block

```
You are AGENT 2E implementing FIX_2-E from Agentic_campaign/FIX_2.md.

Read: Fix_2_prompts/AGENT_2E_VERIFY_HARNESS.md, FIX_2.md §7-E §9 §10,
run_all_daedalus_verifications.py, verify_proposal_engine.py patterns.

Prerequisite: FIX_2-A through 2D merged (or rebase onto combined branch).

Constraints:
- Verification + fixtures ONLY — no production refactors
- Match existing check() style; no inline imports
- Exit 0 on python verification/run_all_daedalus_verifications.py

Deliver: fixture trees + verify_objective_surface.py + proposal_engine extensions + driver registration.
```
