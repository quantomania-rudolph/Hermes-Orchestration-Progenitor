# FIX_1 Wave Campaign — DGM Parent Selection & Program Database

**Authority:** `Agentic_campaign/FIX_1.md` v1.0.0  
**Prompt folder:** `Agentic_campaign/Fix_1_prompts/`  
**Gap IDs closed:** P1-001, P1-004, RG-B003, RG-B005  
**Excludes:** Gating E4 cascade (parallel gating team), FIX_2–FIX_5

---

## Campaign goal

Repair Daedalus P1 so **live archive-mode campaigns sample real `cand_*` parents** after the first gate ACCEPT — not the protected `cold_start::baseline_champion` bootstrap on an incomparable reward scale (~2.313 vs ~0.00037). Unify population telemetry, make DGM parent selection auditable in stdout/journal, and prove fixes with regression tests mirroring `run_gaps_simple_rsi_002`.

---

## Agent roster

| Prompt file | Agent ID | Charter | Primary owned paths |
|-------------|----------|---------|---------------------|
| `AGENT_1A_BOOTSTRAP_NORMALIZATION.md` | FIX_1-A | Bootstrap R08 normalization + parent pool exclusion | `search/program_database.py` (bootstrap/pool), `config/daedalus_config.py` (COLD_START_* only) |
| `AGENT_1B_PARENT_SAMPLER_DIAGNOSTICS.md` | FIX_1-B | DGM weight diagnostics + `archive_propose` logging | `search/parent_sampler.py`, `orchestrator/campaign.py` (log_stage blocks only) |
| `AGENT_1C_POPULATION_STATS.md` | FIX_1-C | Authoritative population telemetry | `search/program_database.py` (`population_stats` only), `state/archive_manager.py` (doc/helpers) |
| `AGENT_1D_PROPOSAL_ENGINE_ORCHESTRATION.md` | FIX_1-D | Cold-start orchestration + complete `diag` | `search/proposal_engine.py`, `orchestrator/epochs/e0_grounding.py` (bootstrap hook only) |
| `AGENT_1E_INTEGRATION_VERIFICATION.md` | FIX_1-E | P1 integration tests + live acceptance harness | `verification/verify_proposal_engine.py`, `verification/live/accept_fix1_parent_selection.py` |

---

## Wave order (maximize safe parallelism)

```text
WAVE 1 (single agent — blocking)
  AGENT_1A  Bootstrap reward R08 alignment + parent_candidates exclusion + E0 migration hook

WAVE 2 (parallel OK after Wave 1 merged)
  AGENT_1B  Parent sampler diagnostics + campaign archive_propose stdout
  AGENT_1C  population_stats unification (touches program_database stats section ONLY)

WAVE 3 (after Wave 2 merged)
  AGENT_1D  proposal_engine diag completeness + E0 grounding bootstrap orchestration

WAVE 4 (after Wave 3 merged — verification only, no production logic)
  AGENT_1E  run_002 regression fixtures + live log acceptance script
```

**Critical path:** `1A → (1B ∥ 1C) → 1D → 1E → live smoke`  
**Do not start FIX_2 agents until FIX_1 Wave 4 passes.**

### Why not all five in parallel?

| Conflict | Resolution |
|----------|------------|
| 1A and 1C both edit `program_database.py` | 1A lands first; 1C restricted to `population_stats()` / stats helpers |
| 1D depends on diag field names from 1B | 1B completes before or with 1D |
| 1E must not edit production modules until A–D done | 1E is last |

---

## Every agent MUST

1. Read **`Agentic_campaign/FIX_1.md`** in full before coding.
2. Read their **`AGENT_1*.md`** prompt end-to-end; do not expand scope beyond owned files.
3. Prepend the **persona block** from their prompt when spun up in Cursor.
4. Exit 0 on:
   ```bash
   cd daedalus
   python verification/verify_proposal_engine.py
   python verification/run_all_daedalus_verifications.py
   ```
5. **Not** edit `orchestrator/epochs/e3_e4_verify.py`, `tools/gate/*`, gating registry, or FIX_2/FIX_3 modules.
6. **Not** weaken `_is_real_accept()` or re-include bootstrap in parent pool after real ACCEPT.
7. Append live evidence to `daedalus/RUN_GAPS.JSON` if campaign still fails after your segment (honesty rule).
8. Re-run verification after fixes — never declare done from a single pass.
9. Imports at top of module — no inline imports unless circular dependency documented.

---

## Shared persona (prepend to every agent)

```text
You are FIX_1 agent [AGENT_ID] — an advanced systems engineer specializing in evolutionary search infrastructure, program-database correctness, and production observability. You have a forensic eye for "green tests, broken campaigns" — wiring that passes unit tests but fails live RSI runs.

Authority: Agentic_campaign/FIX_1.md. Measurement-monopoly gate is unchanged — you do not edit E4 gating.

Your job is surgical: fix the assigned P1 defect with minimal diff, prove it with the verification suite listed in your prompt, and hand off to the next wave. When you see reward-scale mismatch, parent-pool leakage, or ambiguous population counters, you treat them as P0 — open-ended search depends on comparable perf scores (DGM §C.2).

Do not refactor unrelated code. Do not expand scope into FIX_2 site selection, FIX_3 mutator throughput, or graduation (FIX_4).
```

---

## Institutional references (all agents)

| Paper / system | ID | FIX_1 relevance |
|----------------|-----|-----------------|
| **Darwin Gödel Machine** | [arXiv:2505.22954](https://arxiv.org/abs/2505.22954) §C.2 | Parent = sigmoid(perf) × 1/(1+children); perf must be comparable |
| **AlphaEvolve** | [arXiv:2506.13131](https://arxiv.org/abs/2506.13131) §2.5 | Program database, MAP-Elites + islands, prompt parent + scores |
| **FunSearch** | Nature 2023 | Island populations, best-shot prompting from archive |
| **QuantEvolve** | [arXiv:2510.18569](https://arxiv.org/abs/2510.18569) §4 | Behavioral feature map — awareness only (P1-008 out of scope) |

### Open-source reference repos (read for patterns, do not copy blindly)

| Repository | URL | Use |
|------------|-----|-----|
| **jennyzzt/dgm** | https://github.com/jennyzzt/dgm | DGM archive + parent selection semantics |
| **codelion/openevolve** | https://github.com/codelion/openevolve | Evaluator pool, program DB at smaller scale |
| **SakanaAI/evolutionary-model-merge** | https://github.com/SakanaAI/evolutionary-model-merge | Sakana evolutionary archive patterns (context) |

---

## Repo evidence (all agents must skim)

| Artifact | Path |
|----------|------|
| Gap inventory | `daedalus/MISSING.JSON` → `phase_1_proposal_search` |
| Live campaign journal | `daedalus/RUN_GAPS.JSON` → RG-B003, RG-B005 |
| Campaign log | `daedalus/verification/live/run_gaps_campaign_002.log` |
| P1 verifier | `daedalus/verification/verify_proposal_engine.py` |

---

## Merge discipline

1. **Branch naming:** `fix1/agent-1a-bootstrap`, `fix1/agent-1b-diagnostics`, etc.
2. **Merge order:** 1A → (1B + 1C) → 1D → 1E into integration branch `fix1/integration`.
3. **Conflict resolution:** If two agents touched the same line, 1A wins on bootstrap/pool; 1C wins on `population_stats` keys; 1B wins on `select_diagnostics` shape; 1D wins on `propose()` diag assembly.
4. **Integration owner (human or single agent after Wave 4):** Run live smoke (section below) and update `RUN_GAPS.JSON`.

---

## Campaign exit criteria (Definition of Done)

- [ ] `python verification/run_all_daedalus_verifications.py` exit 0 from `daedalus/`
- [ ] `python verification/live/accept_fix1_parent_selection.py` exit 0 (golden log or post-fix dry propose)
- [ ] `archive.json`: `cold_start::baseline_champion.reward` ≈ 0.0 (R08 scale), not 2.313
- [ ] After first real ACCEPT, `archive_propose` logs show `boot_excl=True` and `parent=cand_*` (not bootstrap reversion at epoch 1)
- [ ] `population` vs `archive_size` unambiguous in campaign stdout (`pop=` vs `arch=`)

### Optional live smoke (operator)

```bash
cd daedalus
export DAEDALUS_SEARCH_MODE=archive
export HERMES_RSI_SMOKE=1
python verification/live/run_all_generated_campaigns.py --target simple_rsi_strategy
# Inspect log for forbidden pattern: boot_excl=True + parent=cold_start
```

---

## Handoff to FIX_2

When FIX_1 Wave 4 is green, FIX_2 agents may begin. FIX_2 depends on sane `parent_id` and non-empty lineage for mutation context (P2-001 / RG-C003).

---

## Prompt file index

```
Fix_1_prompts/
  WAVE_CAMPAIGN.md                          ← this file
  AGENT_1A_BOOTSTRAP_NORMALIZATION.md
  AGENT_1B_PARENT_SAMPLER_DIAGNOSTICS.md
  AGENT_1C_POPULATION_STATS.md
  AGENT_1D_PROPOSAL_ENGINE_ORCHESTRATION.md
  AGENT_1E_INTEGRATION_VERIFICATION.md
```

Future: `Fix_2_prompts/` … `Fix_5_prompts/` with same wave pattern.

---

## How to spin up one agent (operator)

1. Open the agent prompt file (e.g. `AGENT_1A_BOOTSTRAP_NORMALIZATION.md`).
2. Prepend the **Shared persona** block above; replace `[AGENT_ID]` with `FIX_1-A`.
3. Paste the full prompt as the user message in a **new Cursor agent session** (one agent per prompt file).
4. Point the agent at workspace root: `C:\Users\Rudol\Desktop\Hermes_Orchestration`.
5. Require exit 0 on verification commands listed in that prompt before merge.
6. Merge to `fix1/integration` in wave order; do not start next wave until prior wave merged.

### Parallelism summary

| Wave | Agents | Parallel? |
|------|--------|-----------|
| 1 | 1A | No |
| 2 | 1B, 1C | Yes (after 1A) |
| 3 | 1D | No (after 2) |
| 4 | 1E | No (after 3) |

### Coordination with gating team

Gating agents (Wave 4–7 in `daedalus/agent_prompts/gating/`) may run **in parallel** with FIX_1 if they do not edit `search/program_database.py`, `parent_sampler.py`, or `proposal_engine.py`. **AGENT_G (E2E promotion)** touches E3/E4 — coordinate merges to avoid conflicts. FIX_1 does not modify gate cascade.
