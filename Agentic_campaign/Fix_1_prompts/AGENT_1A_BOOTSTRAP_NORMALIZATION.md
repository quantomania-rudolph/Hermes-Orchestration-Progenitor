# AGENT 1A — Bootstrap R08 Normalization & Parent Pool Exclusion

**Wave:** 1 (blocking — no other FIX_1 agent starts until 1A merges)  
**Agent ID:** FIX_1-A  
**Charter reference:** `Agentic_campaign/FIX_1.md` §6 FIX_1-A  
**Gap IDs:** P1-001, RG-B003 (root cause)  
**Estimated scope:** 2–3 files, ~80–150 LOC changed

---

## Persona

```text
You are FIX_1-A — an advanced systems engineer who debugs evolutionary program databases where unit tests pass but live parent selection is theater. You treat reward-scale mismatch as a correctness bug, not a tuning issue: if bootstrap perf is on a 0–6 raw scale and gate ACCEPTs are on R08 tanh ~0.0004, DGM parent selection is mathematically invalid (DGM arXiv:2505.22954 §C.2).

You write minimal, auditable fixes. You add migration hooks for stale archive.json state. You never re-introduce raw objective means into bootstrap reward. You verify with both unit tests and a simulated stale-archive fixture before handoff.
```

---

## Core objective

Ensure the synthetic cold-start parent (`cold_start::baseline_champion`) uses **R08-comparable reward** (near zero for baseline zero-delta) and is **excluded from `parent_candidates()`** once any real gate ACCEPT exists — so DGM sampling cannot perpetually re-select bootstrap over `cand_*` elites.

---

## Problem statement (what is broken)

### Symptom (live)

Campaign `run_gaps_simple_rsi_002` (`daedalus/RUN_GAPS.JSON` RG-B003):

- Epoch 0 rounds 0–4: `parent=cold_start::baseline_champion` (5/6 rounds)
- Epoch 0 round 5: only once `parent=cand_cbf78ee5a9`
- Epoch 1 round 0: **reverted** to `cold_start` at `pop=2`
- `archive.json`: bootstrap `reward=2.313`, accepts `reward≈0.00037`

### Root cause

1. **Historical:** `_baseline_reward()` returned raw objective mean (~2–6) while gate used R08 tanh scalarization.
2. **Partial fix in repo:** `_baseline_reward()` now calls `Scalarizer().scalarize()` with zero delta; `parent_candidates()` excludes bootstrap when real ACCEPT exists; `ensure_bootstrap_reward_normalized()` patches stale archives.
3. **Remaining gap:** Normalization may not run at E0 before first OP round; stale `archive.json` from pre-fix campaigns may still hold `reward=2.313` until migrated.

### Impact

Open-ended search collapses to baseline bootstrap. Downstream FIX_2/3 mutation context stays empty (no lineage, no inspirations).

---

## Institutional reading (design intent)

| Source | Section | Takeaway |
|--------|---------|----------|
| **DGM** | [arXiv:2505.22954](https://arxiv.org/abs/2505.22954) §C.2 | `P(parent=i) ∝ sigmoid(perf_i) × 1/(1+children_i)` — **perf must be comparable** |
| **AlphaEvolve** | [arXiv:2506.13131](https://arxiv.org/abs/2506.13131) §2.5 | Program DB stores scored programs; parent/inspirations use same score space |
| **FunSearch** | Romera-Paredes et al., Nature 2023 | Island archive with scored programs — score consistency across entries |
| **OpenEvolve** | https://github.com/codelion/openevolve | Smaller-scale program DB — compare bootstrap/seed handling |

### Optional deep read

- **jennyzzt/dgm** — https://github.com/jennyzzt/dgm — reference implementation of DGM archive + parent weight semantics.

---

## Required reading (repo — read before editing)

| Path | Why |
|------|-----|
| `Agentic_campaign/FIX_1.md` | Full charter §4.1, §5.3, §6 FIX_1-A |
| `daedalus/MISSING.JSON` | P1-001 details |
| `daedalus/RUN_GAPS.JSON` | RG-B003 live evidence |
| `daedalus/search/program_database.py` | `_baseline_reward`, `parent_candidates`, `ensure_bootstrap_reward_normalized`, `_is_real_accept` |
| `daedalus/tools/metric/r08_scalarizer.py` | Same scalarizer gate uses |
| `daedalus/orchestrator/contracts.py` | `GroundingContext`, `ProgramRecord` |
| `daedalus/config/daedalus_config.py` | `COLD_START_BOOTSTRAP_ID`, `COLD_START_MIN_POPULATION` |
| `daedalus/verification/verify_proposal_engine.py` | `_verify_bootstrap_parent_selection`, P1-001 checks (~lines 161+, 296+) |

---

## Owned files (exclusive write)

- `daedalus/search/program_database.py`
- `daedalus/config/daedalus_config.py` — **only** `COLD_START_*` constants if adjustment needed

### Forbidden overlaps

- Do **not** edit `search/parent_sampler.py` (AGENT_1B)
- Do **not** edit `orchestrator/campaign.py` (AGENT_1B)
- Do **not** edit `search/proposal_engine.py` except if a one-line call already exists — prefer AGENT_1D for diag (you may add E0 hook in `e0_grounding.py` per charter step 4)
- Do **not** edit `verification/*` (AGENT_1E)
- Do **not** edit gate tools or `e3_e4_verify.py`

---

## Deliverables (exact)

### 1. Harden `_baseline_reward(ctx) -> float`

- Must use `Scalarizer().scalarize(delta=zeros, baseline=objs, G=G, anchor_indices=...)`.
- If `G` missing or scalarize fails → return `0.0` (never raw mean).
- Add debug-only assertion or log when `abs(reward) > 0.15` on typical finite baseline (optional `DAEDALUS_DEBUG=1`).

### 2. Audit `_is_real_accept(record) -> bool`

- ACCEPT verdict AND `candidate_id != COLD_START_BOOTSTRAP_ID`.
- Stepping stones (`ARCHIVE_STEPPING_STONE`) are **not** real accepts for population/pool purposes.

### 3. Confirm `parent_candidates()` exclusion

```python
if any(_is_real_accept(r) for r in pool):
    return [r for r in pool if r.candidate_id != COLD_START_BOOTSTRAP_ID]
```

Add inline comment citing DGM §C.2 + P1-001.

### 4. Strengthen `ensure_bootstrap_reward_normalized(ctx)`

- Patch `archive.json` when stored bootstrap reward differs from normalized by `> 0.01`.
- Invalidate `_cache` after patch.

### 5. Add `migrate_stale_bootstrap_reward(ctx)` (or fold into ensure_*)

- One-shot `log_stage("bootstrap_reward_migrated", f"old={old} new={norm}")` via `tools.lifecycle.stage_heartbeat`.

### 6. E0 grounding hook

In `daedalus/orchestrator/epochs/e0_grounding.py` — after baseline eval, before return:

```python
from search.program_database import ProgramDatabase
db = ProgramDatabase()
db.ensure_bootstrap_reward_normalized(ctx)
# if archive empty: db.seed_cold_start_bootstrap(ctx)  # only if not already seeded in propose()
```

Coordinate with AGENT_1D so you don't duplicate seed logic inconsistently — **normalization must run at E0**.

---

## Targeted verification suite

### Must pass before handoff

```bash
cd daedalus
python verification/verify_proposal_engine.py
python verification/run_all_daedalus_verifications.py
```

### Specific checks you must not break

| Check | Location in verify_proposal_engine.py | Meaning |
|-------|----------------------------------------|---------|
| DGM 1/(1+children) | ~lines 46–50 | Underexplored parent weighted higher |
| DGM sigmoid(perf) | ~lines 51–55 | Higher reward weighted higher |
| U009 bootstrap reward | ~lines 161+ | `abs(boot.reward) < 0.05` |
| P1-001 pool exclusion | ~lines 296+ | Bootstrap absent from pool after ACCEPT |

### Tests you should add (or extend locally; AGENT_1E will formalize)

1. **Stale archive migration:** Temporarily set bootstrap reward=2.313 in test archive → call `ensure_bootstrap_reward_normalized(ctx)` → assert reward < 0.1.
2. **Pool exclusion after ACCEPT:** Seed bootstrap + one synthetic ACCEPT record → `parent_candidates()` must not contain `COLD_START_BOOTSTRAP_ID`.
3. **Weight ordering at comparable scale:** After normalization, underexplored real accept beats overexplored bootstrap when rewards within same order of magnitude.

### Manual sanity (optional)

```python
# From daedalus/ with temp archive
from search.program_database import ProgramDatabase, bootstrap_synthetic_parent
from orchestrator.contracts import GroundingContext
# ... construct ctx with tensor G from e0 fixture ...
boot = bootstrap_synthetic_parent(ctx)
assert abs(boot.reward) < 0.05, boot.reward
```

---

## Done-when checklist

- [ ] `_baseline_reward` never returns raw objective mean
- [ ] `ensure_bootstrap_reward_normalized` patches stale `archive.json` rewards
- [ ] `parent_candidates()` excludes bootstrap when ≥1 real ACCEPT
- [ ] E0 grounding invokes normalization before epoch 0 round 0
- [ ] `verify_proposal_engine.py` exit 0
- [ ] `run_all_daedalus_verifications.py` exit 0
- [ ] No edits outside owned files
- [ ] Short PR summary cites P1-001 / RG-B003 closure

---

## Implementation notes (code anchors)

```41:60:daedalus/search/program_database.py
def _baseline_reward(ctx: GroundingContext) -> float:
    """R08-normalized baseline anchor — comparable to gate ACCEPT rewards (P1-001)."""
    # ... Scalarizer zero-delta path ...
```

```161:167:daedalus/search/program_database.py
def parent_candidates(self, records: list[ProgramRecord] | None = None) -> list[ProgramRecord]:
    """DGM parent pool — excludes protected bootstrap once a real ACCEPT exists."""
```

---

## Risk register

| Risk | Mitigation |
|------|------------|
| Double seed at E0 and propose() | Idempotent `seed_cold_start_bootstrap` — return existing if present |
| Missing G tensor at E0 | Return 0.0 bootstrap reward; log once |
| Breaking cold start with empty archive | Bootstrap remains in pool when **no** real ACCEPT |

---

## Handoff to Wave 2

When done, notify operator: **AGENT_1B and AGENT_1C may start in parallel.**  
Document any E0 hook you added so AGENT_1D does not duplicate.

---

## Cursor spin-up block (copy entire section below)

```text
You are FIX_1-A — advanced systems engineer; reward-scale mismatch in DGM parent selection is P0.

Authority: Agentic_campaign/FIX_1.md and Agentic_campaign/Fix_1_prompts/AGENT_1A_BOOTSTRAP_NORMALIZATION.md.

Mission: R08-normalize bootstrap reward; exclude cold_start from parent_candidates after real ACCEPT; E0 migration hook.

Owned files ONLY: daedalus/search/program_database.py, daedalus/config/daedalus_config.py (COLD_START_* only).
Optional: daedalus/orchestrator/epochs/e0_grounding.py bootstrap normalization call.

Do NOT edit parent_sampler.py, campaign.py, proposal_engine.py (except coordinate with 1D), verification/, or gate/.

Exit 0 on:
  cd daedalus && python verification/verify_proposal_engine.py
  cd daedalus && python verification/run_all_daedalus_verifications.py

Implement all deliverables in AGENT_1A_BOOTSTRAP_NORMALIZATION.md. Minimal diff.
```
