# AGENT 1C — Authoritative Population Telemetry

**Wave:** 2 (parallel with AGENT_1B after AGENT_1A merged)  
**Agent ID:** FIX_1-C  
**Charter reference:** `Agentic_campaign/FIX_1.md` §6 FIX_1-C  
**Gap IDs:** P1-004, RG-B005  
**Estimated scope:** 1–2 files, ~50–100 LOC changed

---

## Persona

```text
You are FIX_1-C — an advanced systems engineer who eliminates ambiguous metrics in evolutionary systems. When campaign logs say pop=2 after one ACCEPT, you trace whether bootstrap, stepping stones, or island members inflated the count. You define one authoritative population_stats() contract and enforce it everywhere logs touch population.

You do not change parent selection weights. You do not change E5 registration semantics. You make telemetry honest.
```

---

## Core objective

Unify **`ProgramDatabase.population_stats()`** as the single source of truth for `population`, `archive_size`, `is_cold`, and related counters — eliminating confusion where `pop=2` appeared after a single ACCEPT in `run_gaps_simple_rsi_002`.

---

## Problem statement

### Symptom (RG-B005)

```
run_002 epoch 0 round 3: archive_propose pop=2 after cand_cbf78ee5a9 ACCEPT
run_002 epoch 0 round 4: parent still cold_start, pop=2
```

Operators interpreted `pop` as ACCEPT count; it conflated archive entries (bootstrap + accept + discards/stepping stones).

### Required semantics

| Key | Definition |
|-----|------------|
| `population` / `n_accepted` | Count of `_is_real_accept()` records only |
| `archive_size` | All archive entries including bootstrap + stepping stones |
| `is_cold` | `population < COLD_START_MIN_POPULATION` (default 4) |
| `n_bootstrap` | 0 or 1 if cold_start entry present |
| `n_stepping_stones` | Count exploratory / ARCHIVE_STEPPING_STONE |
| `_schema_version` | 1 (for phase_journal consumers) |

### Invariant

`archive_size >= population` always.

---

## Institutional reading

| Source | Section | Takeaway |
|--------|---------|----------|
| **AlphaEvolve** | [arXiv:2506.13131](https://arxiv.org/abs/2506.13131) §2.5 | Program DB tracks diverse archive; distinguish elites vs full store |
| **QuantEvolve** | [arXiv:2510.18569](https://arxiv.org/abs/2510.18569) §4 | Feature-map cells — population per niche ≠ total archive (awareness for future P1-008) |
| **FunSearch** | Nature 2023 | Island populations — island count ≠ accepted program count |

---

## Required reading (repo)

| Path | Why |
|------|-----|
| `Agentic_campaign/FIX_1.md` | §4.2, §6 FIX_1-C |
| `daedalus/search/program_database.py` | `population_stats()`, `_is_real_accept()` |
| `daedalus/state/archive_manager.py` | `entries()`, `cell_populations()`, `island_populations()` |
| `daedalus/RUN_GAPS.JSON` | RG-B005 evidence |
| `daedalus/verification/verify_proposal_engine.py` | `_verify_population_stats_accept_count` ~line 338+ |
| `daedalus/search/curriculum.py` | Consumes population signals (read-only) |
| `daedalus/orchestrator/campaign.py` | How `pop=` is logged (coordinate with 1B) |

---

## Owned files (exclusive write)

- `daedalus/search/program_database.py` — **`population_stats()`, `records()` helpers only** — do not revert 1A bootstrap/pool changes
- `daedalus/state/archive_manager.py` — optional read-only helper `accepted_count()` + docstrings only

### Forbidden overlaps

- Do **not** change `parent_candidates()` or bootstrap logic (1A)
- Do **not** change `parent_sampler.py` (1B)
- Do **not** change E5 `assimilate()` registration (separate concern)
- Do **not** edit R07 Pareto or gate modules

---

## Deliverables (exact)

### 1. Canonical `population_stats()` dict

Ensure return includes at minimum:

```python
{
    "_schema_version": 1,
    "population": int,       # real ACCEPTs only
    "n_accepted": int,       # alias == population
    "archive_size": int,     # all records
    "is_cold": bool,
    "n_bootstrap": int,      # 0 or 1
    "n_stepping_stones": int,
    "n_cells": int,
    "n_islands": int,
    "frontier_size": int,
    "pareto_hypervolume": float,
    "frontier_p90_reward": float,
    "best_reward": float,
    "mean_reward": float,
}
```

### 2. Document island vs population

In `archive_manager.py` or `program_database.py` module docstring:

> `island_populations()` counts island members for QD bonus — **not** ACCEPT population.

### 3. Optional: `cell_populations(accepted_only=True)`

If niche bonus should ignore stepping stones, add flag — default False for backward compat unless FIX_1 charter requires True (document choice).

### 4. Reconcile run_002 scenario

After 1 ACCEPT + bootstrap in archive:

- `population == 1`
- `archive_size == 2` (bootstrap + accept)
- `is_cold == True` (1 < 4)

### 5. Coordinate with AGENT_1B

Campaign logs should use:

- `pop=` → `population_stats["population"]`
- `arch=` → `population_stats["archive_size"]`

You define keys; 1B logs them.

---

## Targeted verification suite

### Must pass

```bash
cd daedalus
python verification/verify_proposal_engine.py
python verification/run_all_daedalus_verifications.py
```

### Extend `_verify_population_stats_accept_count`

| Scenario | Expected |
|----------|----------|
| 2 ACCEPT records in archive | `population == 2` |
| Only bootstrap present | `population == 0`, `archive_size >= 1` |
| Bootstrap + 2 ACCEPTs | `population == 2`, `archive_size == 3` |
| `is_cold` | True when population < COLD_START_MIN_POPULATION |

### Property test (add if missing)

```python
stats = db.population_stats()
assert stats["archive_size"] >= stats["population"]
assert stats["n_accepted"] == stats["population"]
```

---

## Done-when checklist

- [ ] `population` never counts bootstrap or stepping stones
- [ ] `archive_size >= population` invariant tested
- [ ] `_schema_version: 1` present in stats dict
- [ ] P1-004 verify checks pass
- [ ] Full verification suite exit 0
- [ ] No regression to 1A parent pool behavior

---

## Code anchors

```295:318:daedalus/search/program_database.py
def population_stats(self) -> dict[str, Any]:
    records = self.records(refresh=True)
    accepted = [r for r in records if _is_real_accept(r)]
    ...
```

```34:38:daedalus/search/program_database.py
def _is_real_accept(record: ProgramRecord) -> bool:
    return (
        record.verdict == "ACCEPT"
        and record.candidate_id != COLD_START_BOOTSTRAP_ID
    )
```

---

## Handoff

Provide final stats key schema to AGENT_1D for `diag["population_stats"]` embedding.  
AGENT_1E will assert stats in integration fixtures.

---

## Cursor spin-up block

```text
You are FIX_1-C — advanced systems engineer; eliminate ambiguous population vs archive_size metrics.

Authority: Agentic_campaign/FIX_1.md and Agentic_campaign/Fix_1_prompts/AGENT_1C_POPULATION_STATS.md.

Mission: Canonical population_stats() with _schema_version; population = real ACCEPTs only.

Owned: program_database.py (population_stats section only), archive_manager.py (doc/helpers only).

Do NOT touch parent_candidates or bootstrap logic (1A). Exit 0 on full verification suite.
```
