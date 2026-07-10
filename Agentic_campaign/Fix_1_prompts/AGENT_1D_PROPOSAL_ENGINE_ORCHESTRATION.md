# AGENT 1D — ProposalEngine Cold-Start Orchestration & Diag Completeness

**Wave:** 3 (after AGENT_1A + 1B + 1C merged)  
**Agent ID:** FIX_1-D  
**Charter reference:** `Agentic_campaign/FIX_1.md` §6 FIX_1-D  
**Gap IDs:** P1-001 orchestration, RG-B003 diag completeness, U009 cold-start  
**Estimated scope:** 2 files, ~70–130 LOC changed

---

## Persona

```text
You are FIX_1-D — an advanced systems engineer who owns orchestration glue in multi-stage pipelines. You ensure ProposalEngine.propose() executes bootstrap normalization, parent pool construction, and diagnostic export in the correct order — and that E0 grounding prepares archive state before epoch 0 round 0. You treat missing diag keys as contract violations, not logging niceties.

You do not implement multi-site batch proposals (P1-002 deferred). You do not change DGM math (1B) or population definitions (1C).
```

---

## Core objective

Make **`ProposalEngine.propose()`** the reliable orchestrator for cold-start bootstrap, stale reward normalization, parent pool construction, and **complete `diag` export** for campaign journaling — including `bootstrap_excluded`, refreshed `cold_start` flag, and full `parent_selection` block.

---

## Problem statement

### Symptom

`phase_journal` and campaign logs lack audit trail fields. `cold_start=True` persisted after first ACCEPT because stats were read before normalization refresh. E0 may not normalize bootstrap before first OP round — first propose reads stale `reward=2.313`.

### Orchestration order (must be)

1. `population_stats()` (initial)
2. `ensure_bootstrap_reward_normalized(ctx)`
3. `records(refresh=True)`
4. Cold-start seed if empty archive
5. `parent_candidates(records)`
6. Parent sample + `select_diagnostics`
7. Emit complete `diag`

### Failure mode (RG-B003)

`bootstrap_excluded` not computed → operators cannot see pool shrink. `cold_start` uses pre-bootstrap stats.

---

## Institutional reading

| Source | Section | Takeaway |
|--------|---------|----------|
| **AlphaEvolve** | [arXiv:2506.13131](https://arxiv.org/abs/2506.13131) §2.2–2.5 | Prompt sampler reads program DB; orchestrator must sample parent with full context |
| **DGM** | [arXiv:2505.22954](https://arxiv.org/abs/2505.22954) §C.2 | Archive-conditioned parent selection each generation |
| **OpenEvolve** | https://github.com/codelion/openevolve | Study controller/orchestrator loop for DB refresh ordering |

---

## Required reading (repo)

| Path | Why |
|------|-----|
| `Agentic_campaign/FIX_1.md` | §5.2 sequence diagram, §6 FIX_1-D, §8.3 phase_journal |
| `daedalus/search/proposal_engine.py` | Full `propose()` method |
| `daedalus/orchestrator/epochs/e0_grounding.py` | Baseline eval return path |
| `daedalus/search/program_database.py` | Methods called by propose (read 1A/1C outputs) |
| `daedalus/search/parent_sampler.py` | `select_diagnostics` shape from 1B |
| `daedalus/orchestrator/campaign.py` | Consumes `sdiag` from propose |
| `daedalus/verification/verify_proposal_engine.py` | propose integration ~lines 99–120 |

---

## Owned files (exclusive write)

- `daedalus/search/proposal_engine.py`
- `daedalus/orchestrator/epochs/e0_grounding.py` — bootstrap normalization/seed hook only (coordinate with 1A to avoid duplicate logic)

### Forbidden overlaps

- Do **not** edit `parent_sampler.py` (1B)
- Do **not** edit `campaign.py` log format (1B)
- Do **not** edit `verify_proposal_engine.py` (1E)
- Do **not** implement P1-002 multi-site batch

---

## Deliverables (exact)

### 1. Cold-start block (proposal_engine.py ~72–82)

After `ensure_bootstrap_reward_normalized` + `records(refresh=True)`:

- If archive empty: `seed_cold_start_bootstrap(ctx)` → set `diag["cold_start_bootstrap"]` only on **new** seed
- Refresh `stats = db.population_stats()` **after** seed

### 2. Parent selection block (~84–107)

Always populate when `parent_pool` non-empty:

```python
diag["parent_selection"] = {
    **self.parent_sampler.select_diagnostics(
        parent_pool, cell_pops=cell_pops, island_pops=island_pops,
        chosen_id=parent.candidate_id),
    "chosen_weight": weights[idx],
    "chosen_reward": parent.reward,
    "pool_candidate_ids": [r.candidate_id for r in parent_pool],
}
diag["bootstrap_excluded"] = len(parent_pool) < len(records)
diag["parent_pool_size"] = len(parent_pool)
```

### 3. Cold flag semantics

```python
diag["cold_start"] = stats["is_cold"]  # post-normalization, post-seed stats
```

Never use stale pre-bootstrap `stats`.

### 4. E0 grounding hook

After baseline eval in `run_e0()`:

```python
from search.program_database import ProgramDatabase
_pdb = ProgramDatabase()
_pdb.ensure_bootstrap_reward_normalized(ctx)
# Optional: if archive truly empty and campaign expects bootstrap, seed here OR defer to first propose — pick ONE path, document in docstring
```

**Coordinate with AGENT_1A:** avoid double-seed race; idempotent seed is required.

### 5. Journal export slice

Add to `diag` (for phase_journal):

```python
diag["population_stats"] = stats  # includes _schema_version from 1C
```

Optional: pass `n_accepted` into `SearchPlan.prompt_manifest` audit slice if manifest already exists — do not break manifest schema.

### 6. Operator + site blocks unchanged

Do not regress operator_sampler, site resolution, or prompt_sampler.build paths.

---

## Targeted verification suite

### Must pass

```bash
cd daedalus
python verification/verify_proposal_engine.py
python verification/run_all_daedalus_verifications.py
python verification/verify_async_proposal.py   # regression — parent diag still present
```

### Specific assertions to satisfy

| Test | Assertion |
|------|-----------|
| propose returns SearchPlan | Existing ~line 114 |
| diag contains population_stats | Existing ~line 120 |
| parent_selection in diag | When pool non-empty |
| bootstrap_excluded | True after synthetic ACCEPT in fixture |
| cold_start uses refreshed stats | After seed, cold=True when population < 4 |
| Source inspect | `ensure_bootstrap_reward_normalized` call present in propose |

### Integration scenario (manual or for 1E)

1. Empty archive → propose → `parent_id == cold_start::baseline_champion`, `bootstrap_excluded == False`
2. Add ACCEPT to archive → propose → `bootstrap_excluded == True`, parent starts with `cand_`

---

## Done-when checklist

- [ ] Every successful propose with non-empty pool returns complete `parent_selection` diag
- [ ] `bootstrap_excluded=True` after first real ACCEPT
- [ ] E0 normalizes bootstrap before epoch 0 round 0
- [ ] `cold_start` diag reflects post-normalization stats
- [ ] `verify_async_proposal.py` exit 0 (no diag regression)
- [ ] Full verification suite exit 0

---

## Code anchors

```66:107:daedalus/search/proposal_engine.py
def propose(self, *, ctx: GroundingContext, graph: dict[str, Any], target: Target,
            cursor_available: bool = False) -> tuple[SearchPlan | None, bool, dict[str, Any]]:
    # ---- 0) cold-start bootstrap ...
    # ---- 1) parent selection (DGM) ...
```

```212:234:Agentic_campaign/FIX_1.md
sequenceDiagram for parent selection data flow
```

---

## Cross-agent coordination

| Agent | Field / behavior you consume |
|-------|------------------------------|
| 1A | `ensure_bootstrap_reward_normalized`, `parent_candidates` |
| 1B | `select_diagnostics` keys |
| 1C | `population_stats` schema with `_schema_version` |

---

## Handoff

When done, notify operator: **AGENT_1E may begin.**  
Provide list of diag keys for golden-log parser.

---

## Cursor spin-up block

```text
You are FIX_1-D — advanced systems engineer; ProposalEngine.propose() orchestration order is the contract.

Authority: Agentic_campaign/FIX_1.md and Agentic_campaign/Fix_1_prompts/AGENT_1D_PROPOSAL_ENGINE_ORCHESTRATION.md.

Mission: Complete diag export (parent_selection, bootstrap_excluded, refreshed cold_start); E0 hook.

Owned: daedalus/search/proposal_engine.py, e0_grounding.py (bootstrap hook only).

Exit 0 on verify_proposal_engine.py, verify_async_proposal.py, run_all_daedalus_verifications.py.
```
