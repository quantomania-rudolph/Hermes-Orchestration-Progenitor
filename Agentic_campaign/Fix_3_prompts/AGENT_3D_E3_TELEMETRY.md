# AGENT 3D — E3 Timing Telemetry & Stage Heartbeat (RG-A002 partial)

---

## Persona

You are an **advanced systems engineer** who eliminates multi-minute black boxes in live campaigns. E3 between `E3_mutate start` and `E3_done` must be decomposable: flash vs rescan vs apply vs rewrite vs pre-gate vs idle saved. You wire journal fields and operator-facing stdout so RG-A001 regressions are visible in one log line, not post-hoc forensics.

---

## Core objective

**Extend E3 sub-stage telemetry** into `CandidateEvaluation.stats`, consolidate `e3_timings` merge across E3 return paths, and emit `E3_breakdown` stdout when `DAEDALUS_STAGE_HEARTBEAT=1`. Partial close of **RG-A002** at the E3 layer only (E4 cascade is FIX_4 / gating).

---

## Problem statement

`RG-A002`: multi-minute gap between `E3_done` and next `op_round` with no sub-stage visibility.

**Existing hooks (build on, do not replace):**

- `stage_timer(f"E3_mutate:{operator}")` in `e3_e4_verify.py`
- `CandidateBranch.e3_timings` with `spawn_ms`, `flash_ms`, `apply_ms`
- `stage_heartbeat.log_stage` in campaign driver

**Gap:** Missing `rescan_ms`, `rewrite_spawn_ms`, `pre_gate_ms`, `pre_gate_spawns`; no consolidated merge on INFRA/failure paths; no `E3_breakdown` operator line.

---

## Reading list (read before coding)

### Charter & gaps

| Path | Focus |
|------|-------|
| `Agentic_campaign/FIX_3.md` | §7 Segment D, §12 Appendix A stats schema |
| `daedalus/RUN_GAPS.JSON` | RG-A002, RG-A001 timing context |

### Code anchors

| Path | Focus |
|------|-------|
| `daedalus/orchestrator/epochs/e3_e4_verify.py` | E3 wrapper, stats merge, `stage_timer` |
| `daedalus/agents/mutator.py` | Read-only — consumes `e3_timings` dict from 3B |
| `daedalus/agents/pre_gate_review.py` | D-3 `heartbeat_if_elapsed` in long loop |
| `daedalus/tools/lifecycle/stage_heartbeat.py` | `stage_timer`, `log_stage`, `heartbeat_if_elapsed` |
| `daedalus/orchestrator/campaign.py` | D-4 phase journal at `E3_done` |
| `daedalus/RUN_FILES.md` | D-5 field documentation |

### Institutional & OSS

- **AlphaEvolve** (arXiv:2506.13131) — §2.6 async pipeline observability
- **Gödel Machine** — proof/search phases must be measurable separately
- [OpenEvolve](https://github.com/codelion/openevolve) — eval stage timing patterns

---

## Owned files (exclusive write)

| File | Action |
|------|--------|
| `daedalus/orchestrator/epochs/e3_e4_verify.py` | D-1 consolidate `_e3_timings` merge; D-2 `log_stage("E3_breakdown")` |
| `daedalus/agents/pre_gate_review.py` | D-3 heartbeat inside long pre-gate loop only |
| `daedalus/orchestrator/campaign.py` | D-4 phase journal includes `e3_timings` at assimilate hook |
| `daedalus/RUN_FILES.md` | D-5 document journal fields |

---

## Forbidden overlaps

- Do **not** change pre-gate skip policy logic (FIX_3-B owns behavior; 3D only adds heartbeat)
- Do **not** modify `prompt_sampler.py` (FIX_3-A adds E3_context log after 3D lands)
- Do **not** wire E4 cascade telemetry (FIX_4 / gating)

---

## Implementation checklist

### Target journal schema (`CandidateEvaluation.stats`)

```json
{
  "e3_timings": {
    "mutate_total_ms": 403700,
    "spawn_ms": 95000,
    "flash_ms": 95000,
    "rescan_ms": 120,
    "apply_ms": 0,
    "rewrite_spawn_ms": 0,
    "pre_gate_ms": 118000,
    "pre_gate_spawns": 1
  },
  "work_hits": 3,
  "llm_model_arm": "flash",
  "prompt_manifest": { "...": "..." },
  "inspiration_count": 1,
  "mutation_context_briefed": true
}
```

### Stdout contract

| Event | Format |
|-------|--------|
| Mutate start/end | `[daedalus:TS] E3_mutate:REFACTOR start` / `done (Xs)` |
| Sub-stage summary | `[daedalus:TS] E3_breakdown — spawn=95s pre_gate=0s apply=0s idle_saved=180s` |

Note: `E3_context` line is owned by **3A** — leave hook point or stub comment if merging before 3A.

### Tasks

1. **D-1** Merge mutator `e3_timings` on success AND INFRA/failure return paths.
2. **D-2** `log_stage("E3_breakdown", detail=...)` after mutate when `DAEDALUS_STAGE_HEARTBEAT=1`.
3. **D-3** `heartbeat_if_elapsed` in pre-gate loop — no silent gaps > 60s.
4. **D-4** Phase journal at `E3_done` includes `e3_timings`.
5. **D-5** Document fields in `RUN_FILES.md`.

---

## Verification suite (must all pass)

### Primary gates

```bash
cd daedalus
python verification/run_all_daedalus_verifications.py
python verification/verify_mutator_context.py
```

### Agent-specific checks (3E may formalize E-4)

| Check | Expected |
|-------|----------|
| Source inspect | `e3_timings` keys in `e3_e4_verify` stats merge |
| Source inspect | `log_stage("E3_breakdown"` present |
| Journal shape | ACCEPT/DISCARD row includes `e3_timings` with ≥3 keys |
| Heartbeat | No >60s silent gap during simulated long pre-gate (unit/mock) |

### Live validation

```bash
export DAEDALUS_STAGE_HEARTBEAT=1
# run campaign — every E3 round emits E3_breakdown
```

---

## Done-when criteria

- [ ] `e3_timings` consolidated on all E3 return paths
- [ ] `E3_breakdown` emitted when heartbeat enabled
- [ ] Phase journal carries `e3_timings`
- [ ] `RUN_FILES.md` updated
- [ ] Verifiers exit 0

---

## Cursor spin-up block

```
You are AGENT 3D implementing FIX_3 Segment D from Agentic_campaign/FIX_3.md.

Read: Fix_3_prompts/AGENT_3D_E3_TELEMETRY.md, FIX_3.md §7,
e3_e4_verify.py, stage_heartbeat.py, pre_gate_review.py, campaign.py.

Prerequisite: FIX_3-B merged (mutator emits rescan_ms, pre_gate_ms, etc.).

Constraints:
- Telemetry only — do not change pre-gate skip policy (3B)
- Exit 0 on verification/run_all_daedalus_verifications.py + verify_mutator_context.py
- E4 cascade out of scope

Deliver: e3_timings merge + E3_breakdown stdout + heartbeat + RUN_FILES.md docs.
```
