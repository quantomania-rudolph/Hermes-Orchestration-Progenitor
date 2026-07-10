# AGENT 5D — EM Epoch Scheduling + Live Campaign meta_ran=true Proof (P4-001)

---

## Persona

You are an **advanced systems engineer** who proves **meta epochs actually run** in live campaigns — not just green offline verifiers. `DAEDALUS_META_MODE=agent_search` configured but `meta_ran=false` is a critical failure. You wire campaign summary truth, phase journal META entries, and operator runbooks so epoch index 2+ executes `run_em` → `run_meta_agent_search`.

---

## Core objective

**Execute EM epoch at campaign index ≥2** and prove `meta_ran=true` with journal artifacts (`searcher_promoted`, `patch_source`, `frozen_corpus_size`, replay metrics). Close **P4-001 / RG-D001**.

---

## Problem statement

| Symptom | Evidence |
|---------|----------|
| META never ran | `RUN_GAPS run_status.meta_ran=false` |
| Campaign aborted early | `run_002` aborted before epoch index 2 |
| Cadence misunderstood | First META at `epoch_index % META_EPOCH_CADENCE == 0` where index > 0; cadence=2 → index 2, 4, … |

**Scheduling (`r38_epoch_controller.py`):**

```python
is_meta = epoch_index > 0 and (epoch_index % META_EPOCH_CADENCE == 0)
# META_EPOCH_CADENCE = 2 (default)
```

| Index | Type |
|-------|------|
| 0, 1 | OP |
| 2, 4 | **META** |
| 3 | OP |

---

## Reading list (read before coding)

### Charter & gaps

| Path | Focus |
|------|-------|
| `Agentic_campaign/FIX_5.md` | §9 Segment D, §15 success criteria |
| `daedalus/MISSING.JSON` | P4-001 critical |
| `daedalus/RUN_GAPS.JSON` | RG-D001 |

### Code anchors

| Path | Focus |
|------|-------|
| `daedalus/orchestrator/epochs/em_meta.py` | `run_em`, `_run_em_agent_search` |
| `daedalus/orchestrator/campaign.py` | `start(max_epochs)`, summary, phase journal |
| `daedalus/orchestrator/r38_epoch_controller.py` | `is_meta` scheduling |
| `daedalus/meta/meta_agent_search.py` | `run_meta_agent_search` entry |
| `daedalus/verification/live/run_all_generated_campaigns.py` | Live sweep driver |
| `daedalus/config/daedalus_config.py` | `META_EPOCH_CADENCE`, `DAEDALUS_META_MODE` |

### Institutional & OSS

- **ADAS** (arXiv:2408.08435) — meta-agent epoch interleaved with task epochs
- **AlphaEvolve** (arXiv:2506.13131) — co-evolved program DB + meta epochs
- **DGM** (arXiv:2505.22954) — self-improvement loop scheduling
- **Gödel Machine** — meta-search as separate proof phase

### Gating cross-ref

- `daedalus/agent_prompts/gating/AGENT_D_META_RSI.md` — G6-meta gate policy

---

## Owned files (exclusive write)

| File | Action |
|------|--------|
| `daedalus/orchestrator/campaign.py` | `meta_ran`, `meta_epochs` in summary; META phase journal |
| `daedalus/orchestrator/epochs/em_meta.py` | Diagnostics, `EpochResult(is_meta=True)` |
| `daedalus/orchestrator/r38_epoch_controller.py` | Scheduling clarity / logging if needed |
| `daedalus/verification/live/run_all_generated_campaigns.py` | Env defaults for meta live runs |
| `daedalus/RUN_GAPS.JSON` | methodology.env template for meta |

---

## Forbidden overlaps

- Do **not** modify corpus freeze (FIX_5-A)
- Do **not** modify replay rounds (FIX_5-B)
- Do **not** modify LLM mutator core (FIX_5-C)
- Do **not** deprecate primitive mode logic (FIX_5-E owns P4-T002)
- Do **not** enable `DAEDALUS_META_APPLY_PATCH=1` by default

---

## Implementation checklist

### Campaign summary enhancement

```python
"meta_ran": any(r.is_meta for r in results),
"meta_accepted": sum(r.accepted for r in results if r.is_meta),
"meta_epochs": [r.epoch_index for r in results if r.is_meta],
```

Align `RUN_GAPS.JSON run_status.meta_ran` with actual execution.

### Required proof artifacts (epoch ≥2)

```json
{
  "meta_ran": true,
  "searcher_promoted": true,
  "patch_source": "llm_log_conditioned",
  "compile_ok": true,
  "frozen_corpus_size": 8,
  "replay": { "candidate": { "n_rounds": 4, "win_vs_champion": true } },
  "repo_patch_applied": false
}
```

### phase_journal at META boundary

```json
{
  "phase": "epoch_complete",
  "epoch": 2,
  "target": "META",
  "searcher_promoted": true,
  "patch_source": "llm_log_conditioned",
  "frozen_corpus_size": 8
}
```

### EM integration

- `campaign.start(max_epochs=6)` → META at 2 and 4 if not halted
- EM debits ledger: 500 tokens, category `meta`
- `state.write_counters(em_counter=epoch_index)`
- Journal `META_AGENT_SEARCH` record

### Live run command (document in RUN_FILES)

```bash
export HERMES_CURSOR_EXECUTION=wsl_native
export DAEDALUS_META_MODE=agent_search
export DAEDALUS_META_OFFLINE=0
export DAEDALUS_META_APPLY_PATCH=0
python verification/live/run_all_generated_campaigns.py --target simple_rsi_strategy
```

**Precondition:** FIX_1–4 complete; ≥8 journal ACCEPTs; FIX_5-A/B/C merged.

---

## Verification suite (must all pass)

### Offline gates

```bash
cd daedalus
python verification/verify_meta_mutation.py
python verification/run_all_daedalus_verifications.py
```

### Agent-specific checks

| Check | Expected |
|-------|----------|
| Source inspect | `meta_mode: agent_search` in `run_em` diagnostics |
| Summary fields | `meta_ran` computed from `EpochResult.is_meta` |
| Scheduling | Epoch index 2 planned as META with cadence=2 |
| P4-T002 partial | `DAEDALUS_LEGACY_META` gate in verifier |

### Live acceptance (required for FIX_5 closeout)

- Campaign reaches epoch index 2 without killswitch halt
- stdout `searcher_code_promoted` OR honest `candidate_discarded` with `n_rounds > 0`
- Provenance journal for `operator=META_AGENT_SEARCH`
- If promoted: `apply_champion_for_op_epoch` at next OP epoch start

### RUN_GAPS closeout

```json
{"gap_refs": ["RG-D001"], "status": "closed_fix_5", "evidence": "meta_ran=true epoch=2"}
```

---

## Done-when criteria

- [ ] `meta_ran=true` in campaign summary after live run
- [ ] META phase journal entries emitted
- [ ] `max_epochs >= 3` documented for first META
- [ ] EM diagnostics complete with replay metrics
- [ ] RG-D001 evidence appended to RUN_GAPS after live proof

---

## Cursor spin-up block

```
You are AGENT 5D implementing FIX_5 Segment D from Agentic_campaign/FIX_5.md.

Read: Fix_5_prompts/AGENT_5D_EM_SCHEDULING.md, FIX_5.md §9,
em_meta.py, campaign.py, r38_epoch_controller.py, RUN_GAPS RG-D001.

Prerequisite: FIX_5-A, 5-B, 5-C merged; FIX_1–4 live journal ≥8 ACCEPTs.

Constraints:
- meta_ran must reflect actual EM execution — no optimistic true
- DAEDALUS_META_APPLY_PATCH default 0
- Exit 0 on verify_meta_mutation.py + run_all_daedalus_verifications.py

Deliver: campaign summary meta fields + phase journal + live runbook + RG-D001 proof path.
```
