# AGENT 5C — meta_mutator_llm Default + Deterministic Fallback Offline (P4-002, P4-007)

---

## Persona

You are an **advanced systems engineer** who separates **CI-safe offline paths** from **live LLM self-modification**. DGM §C.3 requires foundation-model-proposed patches on real whitelisted source — deterministic constant-insert is fallback only, labeled honestly. You wire Cursor unified diffs with budget gates and never claim `llm_log_conditioned` when offline fallback ran.

---

## Core objective

**Make LLM unified-diff meta mutation the live default** (`patch_source=llm_log_conditioned`) with deterministic `deterministic_log_conditioned_fallback` for `DAEDALUS_META_OFFLINE=1` and CI. Close **P4-002 / P4-007 / RG-D002**.

---

## Problem statement

| Symptom | Evidence |
|---------|----------|
| No LLM patches in live | `source=deterministic_log_conditioned` in pre-fix runs |
| META configured but static | Only `_META_EXPLORATION_DEFAULT`, `META_PROMPT_INSPIRATION_K` patched |
| `DAEDALUS_META_MODE=agent_search` never produces LLM diff | RG-D002 |

**Current partial state:** `meta_mutator.py` defaults to `meta_mutator_llm` when offline≠1 and Cursor available — needs live proof and hardened fallback labeling.

---

## Reading list (read before coding)

### Charter & gaps

| Path | Focus |
|------|-------|
| `Agentic_campaign/FIX_5.md` | §8 Segment C, P4-007 flow table |
| `daedalus/MISSING.JSON` | P4-002, P4-007 |
| `daedalus/RUN_GAPS.JSON` | RG-D002 |

### Code anchors

| Path | Focus |
|------|-------|
| `daedalus/meta/meta_mutator.py` | `propose_searcher_patch`, offline fallback |
| `daedalus/meta/meta_mutator_llm.py` | `propose_searcher_patch_llm`, prompt, diff extract |
| `daedalus/agents/meta_mutator_prompt.py` | `build_meta_mutator_prompt` |
| `daedalus/meta/log_analyzer.py` | `MetaProblemStatement` |
| `daedalus/meta/meta_prompt_db.py` | `champion_directive()` |
| `daedalus/agents/cursor_cli.py` | `run_agent_cli` label `meta_mutator` |
| `daedalus/agents/mutator_diff.py` | `extract_unified_diff` |
| `daedalus/bridge/diff_apply.py` | `apply_unified_diff` validation |

### Institutional & OSS

- **DGM** (arXiv:2505.22954 §C.3) — eval logs → feature proposal → implement patch
- **AlphaEvolve** (arXiv:2506.13131) — meta-prompt conditioning via `MetaPromptDB`
- **ADAS** (arXiv:2408.08435) — meta-agent writes executable code changes
- **Gödel Machine** — patch must apply cleanly before acceptance
- [jennyzzt/dgm](https://github.com/jennyzzt/dgm) — LLM codebase edit loop

---

## Owned files (exclusive write)

| File | Action |
|------|--------|
| `daedalus/meta/meta_mutator.py` | Decision tree, fallback labeling, budget hook |
| `daedalus/meta/meta_mutator_llm.py` | LLM path hardening, `patch_source` truth |
| `daedalus/agents/meta_mutator_prompt.py` | Prompt enrichment if needed |
| `daedalus/verification/verify_meta_mutation.py` | P4-007 mock path; offline CI path |

---

## Forbidden overlaps

- Do **not** modify `historical_corpus.py` (FIX_5-A)
- Do **not** modify `mini_op_replay.py` (FIX_5-B)
- Do **not** widen META whitelist (FIX_5-E)
- Do **not** bypass MetaSafety boundary / R33

---

## Implementation checklist

### Decision tree

```
DAEDALUS_META_OFFLINE == "1"?
  YES → _propose_searcher_patch_offline (deterministic_log_conditioned_fallback)
  NO  → propose_searcher_patch_llm(...)
          None? → offline fallback with warning
          MetaPatchProposal source=llm_log_conditioned
```

### LLM path steps

| Step | Implementation |
|------|----------------|
| Read | `read_whitelisted_source(rel)` — real file content |
| Condition | `log_analyzer`, parent manifest, `MetaPromptDB.champion_directive()` |
| Invoke | `run_agent_cli` label `meta_mutator` |
| Parse | `extract_unified_diff` |
| Validate | Diff applies to all `target_paths`; content hashes recorded |
| Budget | `min(budget_tokens, META_REPLAY_BUDGET_TOKENS * 0.15)` |

### Offline fallback targets

- `search/operator_sampler.py` → `_META_EXPLORATION_DEFAULT`
- `search/prompt_sampler.py` → `META_PROMPT_INSPIRATION_K`
- `search/experience_replay.py` → `_META_REPLAY_K`

Label: `deterministic_log_conditioned_fallback` + `_log.warning`.

### Environment matrix

| Env | Expected `patch_source` |
|-----|-------------------------|
| `DAEDALUS_META_OFFLINE=1` | `deterministic_log_conditioned_fallback` |
| Live WSL + Cursor + key | `llm_log_conditioned` |
| Live without Cursor | fallback (logged) |

---

## Verification suite (must all pass)

### Primary gates

```bash
cd daedalus
python verification/verify_meta_mutation.py
python verification/run_all_daedalus_verifications.py
```

### Agent-specific checks

| Check | Expected |
|-------|----------|
| P4-007 | Mock LLM path produces applicable diff |
| Offline CI | `DAEDALUS_META_OFFLINE=1` → deterministic fallback only |
| Source inspect | `llm_log_conditioned` string in success path |
| Budget | Token cap referenced in meta_mutator_llm |
| Regression | M001 real diff on whitelisted source still passes |

### Live acceptance

Journal `extra.patch_source == "llm_log_conditioned"` on meta attempt; stdout `meta_mutator_llm: LLM patch source=llm_log_conditioned`.

---

## Done-when criteria

- [ ] Live path defaults to LLM when Cursor available
- [ ] Offline/CI uses deterministic fallback with honest labeling
- [ ] `verify_meta_mutation` P4-007 passes
- [ ] Budget gate enforced per LLM call
- [ ] No whitelist widening in this segment

---

## Cursor spin-up block

```
You are AGENT 5C implementing FIX_5 Segment C from Agentic_campaign/FIX_5.md.

Read: Fix_5_prompts/AGENT_5C_META_MUTATOR_LLM.md, FIX_5.md §8,
meta_mutator.py, meta_mutator_llm.py, meta_mutator_prompt.py, verify_meta_mutation P4-007.

Parallel with 5A allowed (disjoint files). Merge before 5D live proof.

Constraints:
- patch_source must be truthful — no llm label on offline fallback
- Exit 0 on verify_meta_mutation.py + run_all_daedalus_verifications.py
- MetaSafety boundary unchanged

Deliver: LLM default path + labeled offline fallback + P4-007 verifier + budget gate.
```
