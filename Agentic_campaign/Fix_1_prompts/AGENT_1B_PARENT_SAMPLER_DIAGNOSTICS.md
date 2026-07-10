# AGENT 1B — DGM Weight Diagnostics & Campaign `archive_propose` Logging

**Wave:** 2 (parallel with AGENT_1C after AGENT_1A merged)  
**Agent ID:** FIX_1-B  
**Charter reference:** `Agentic_campaign/FIX_1.md` §6 FIX_1-B  
**Gap IDs:** RG-B003 (observability), campaign audit trail  
**Estimated scope:** 2 files, ~60–120 LOC changed

---

## Persona

```text
You are FIX_1-B — an advanced systems engineer obsessed with observability in stochastic search systems. You believe if operators cannot see chosen_probability, pool composition, and bootstrap_excluded in live logs, parent selection bugs will recur silently. You extend diagnostics without changing DGM weight ordering on synthetic fixtures. You ensure async and sequential campaign paths log identical parent fields.

You do not tune DGM constants without documenting in MISSING.JSON. You do not fix bootstrap reward scale (that was 1A).
```

---

## Core objective

Make **DGM parent selection auditable** during live campaigns by extending `ParentSampler.select_diagnostics()` and unifying `campaign.py` `archive_propose` log lines (sequential + async) to include `p=` (chosen_probability), `boot_excl=`, `pop=`, `arch=`, and weight breakdown fields.

---

## Problem statement

### Symptom

`run_gaps_campaign_002.log` shows:

```
archive_propose — parent=cold_start::baseline_champion op=REFACTOR cold=True pop=2
```

Missing: `chosen_probability`, `bootstrap_excluded`, explicit `archive_size`, entropy, pool IDs.

### Impact

Operators cannot distinguish "bootstrap legitimately in pool" vs "bootstrap incorrectly dominating." Debugging RG-B003 required manual archive.json inspection. Async eval path (`_run_op_rounds_async`) logs fewer fields than sequential path.

### What is NOT broken

DGM formula in `parent_weight()` — sigmoid × 1/(1+children) × niche × island — is implemented and unit-tested. **Do not change weight ordering** unless fixing an obvious bug.

---

## Institutional reading

| Source | Section | Takeaway |
|--------|---------|----------|
| **DGM** | [arXiv:2505.22954](https://arxiv.org/abs/2505.22954) §C.2 | Parent weights must be inspectable; archive drives open-ended search |
| **AlphaEvolve** | [arXiv:2506.13131](https://arxiv.org/abs/2506.13131) §2.6 | Throughput pipeline needs transparent evaluator/parent telemetry |
| **OpenEvolve** | https://github.com/codelion/openevolve | Study logging patterns for generation/selection metrics |

---

## Required reading (repo)

| Path | Why |
|------|-----|
| `Agentic_campaign/FIX_1.md` | §6 FIX_1-B, §8.2 expected log lines |
| `daedalus/search/parent_sampler.py` | `parent_weight`, `select_diagnostics`, `ParentSampler.sample` |
| `daedalus/orchestrator/campaign.py` | `log_stage("archive_propose", ...)` ~lines 200–206, 296–298 |
| `daedalus/search/proposal_engine.py` | `diag["parent_selection"]` assembly (read-only; coordinate field names with 1D) |
| `daedalus/RUN_GAPS.JSON` | RG-B003, live_monitoring_log |
| `daedalus/config/daedalus_config.py` | `PARENT_SIGMOID_*`, `PARENT_SAMPLE_TEMPERATURE` |
| `daedalus/verification/verify_proposal_engine.py` | Campaign wiring inspect ~line 125 |

---

## Owned files (exclusive write)

- `daedalus/search/parent_sampler.py`
- `daedalus/orchestrator/campaign.py` — **only** `log_stage("archive_propose", ...)` blocks in `_run_op_epoch` and `_run_op_rounds_async`

### Forbidden overlaps

- Do **not** edit `program_database.py` (1A / 1C)
- Do **not** edit `proposal_engine.py` diag assembly (1D) — but **coordinate** field names: `chosen_probability`, `entropy`, `bootstrap_excluded`
- Do **not** edit verification scripts (1E)

---

## Deliverables (exact)

### 1. Extend `select_diagnostics()` return dict

Add fields (minimum):

| Field | Type | Description |
|-------|------|-------------|
| `chosen_probability` | float | Normalized weight of chosen parent in [0,1] |
| `chosen_weight` | float | Unnormalized w_i (already partially present) |
| `chosen_reward` | float | Parent record reward |
| `entropy` | float | Shannon entropy of weight distribution |
| `min_probability` | float | Min weight in pool |
| `max_probability` | float | Max weight in pool |
| `n_candidates` | int | Pool size |
| `weight_rank` | int | 1 = highest weight in pool |
| `pool_ids` | list[str] | Cap at 8 IDs for logs |

### 2. Add `weight_breakdown(record, cell_pops, island_pops) -> dict`

For journal/debug:

```python
{"s_i": ..., "h_i": ..., "niche_factor": ..., "island_factor": ..., "w_i": ...}
```

Use existing `parent_weight()` decomposition — expose components already computed internally or refactor minimally.

### 3. Update sequential `archive_propose` log (campaign.py)

Target format:

```text
archive_propose — parent=cand_xxx p=0.85 weight=1.2 pool=2 boot_excl=True op=REFACTOR cold=True pop=1 arch=2
```

Pull from `sdiag.get("parent_selection")` and `sdiag.get("population_stats")`.

### 4. Parity async path

`_run_op_rounds_async` must log **identical** parent fields as sequential path.

### 5. Temperature journal

When `parent_temperature` overridden via meta champion (`apply_champion_for_op_epoch`), include effective temperature in diagnostics dict (key: `effective_temperature`).

### 6. Document reward precondition

Module docstring or comment on `parent_weight()`: incoming `record.reward` must be R08 tanh gate-scale (FIX_1-A responsibility).

---

## Targeted verification suite

### Must pass

```bash
cd daedalus
python verification/verify_proposal_engine.py
python verification/run_all_daedalus_verifications.py
```

### Add to verify_proposal_engine.py (or local test file for 1E to merge)

| Test | Assertion |
|------|-----------|
| Diagnostics shape | `chosen_probability` in [0,1] for 3-record pool |
| Entropy sanity | `entropy > 0` when weights differ |
| Source inspect | `"chosen_probability"` or `"p="` in `campaign.py` `_run_op_epoch` source |
| Async parity | Same fields in `_run_op_rounds_async` log_stage string |

### Regression guards

- DGM ordering tests in verify_proposal_engine (~lines 46–56) must remain green.
- Parent sampling explores ≥3 distinct lineages over 50 samples — must remain green.

### Manual log review

After a dry `propose()` integration test, confirm diag contains:

```python
assert "chosen_probability" in diag.get("parent_selection", {})
```

---

## Done-when checklist

- [ ] Every sequential `archive_propose` log includes `p=` and `boot_excl=`
- [ ] Async path logs match sequential fields
- [ ] `select_diagnostics` returns entropy + chosen_probability
- [ ] No change to DGM weight ordering on existing synthetic fixtures
- [ ] Full verification suite exit 0
- [ ] No edits outside owned files

---

## Code anchors

```57:75:daedalus/search/parent_sampler.py
def parent_weight(record: ProgramRecord, *, cell_pops: dict[str, int],
                  island_pops: dict[int, int]) -> float:
    """Unnormalized DGM weight w_i = s_i * h_i, with QD/island bonuses."""
```

```200:206:daedalus/orchestrator/campaign.py
# log_stage("archive_propose", ...) — extend this block
```

---

## Handoff

Notify AGENT_1D: final `diag["parent_selection"]` key names are stable.  
AGENT_1E will add golden-log parser expecting `p=` and `boot_excl=`.

---

## Cursor spin-up block

```text
You are FIX_1-B — advanced systems engineer; DGM parent selection must be auditable in live logs.

Authority: Agentic_campaign/FIX_1.md and Agentic_campaign/Fix_1_prompts/AGENT_1B_PARENT_SAMPLER_DIAGNOSTICS.md.

Mission: Extend select_diagnostics(); unify archive_propose log lines (sequential + async) with p=, boot_excl=, pop=, arch=.

Owned files ONLY: daedalus/search/parent_sampler.py, daedalus/orchestrator/campaign.py (log_stage blocks only).

Do NOT change DGM weight ordering on synthetic fixtures. Do NOT edit program_database.py.

Exit 0 on verify_proposal_engine.py and run_all_daedalus_verifications.py from daedalus/.
```
