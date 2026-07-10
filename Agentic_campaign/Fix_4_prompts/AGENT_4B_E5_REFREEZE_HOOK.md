# AGENT 4B — E5 Assimilate Hook + Epoch Boundary Re-freeze

---

## Persona

You are an **advanced systems engineer** who closes the **single code reality** gap between sandbox, generated, and frozen trees. Without epoch refreeze, epoch N+1 mutates from stale `frozen/baseline` while `generated/` holds evolved code — false progress. You wire E5 graduation at the correct layer (after R51+R34, before journal) and trigger `pin_baseline` when promotions occur.

---

## Core objective

**Preserve E5 graduation hook ordering**, populate full graduation journal payload from 4A's result, and add **epoch-boundary re-freeze** via `Campaign._on_op_epoch_complete` + `pin_baseline`. Close **X-002 / RG-F001** (divergent code realities).

---

## Problem statement

**Three trees, broken operator experience:**

```
generated/  → pin_baseline → frozen/ → copy_baseline → sandbox/branches/cand_*
ACCEPT → archive + journal (generated/ NEVER updated)
```

After graduation (when enabled), `generated/` updates but **next epoch** still copies stale frozen unless refrozen.

**E5 current hook (lines 46–52):** calls `graduate_branch_to_target` when `DAEDALUS_GRADUATE_TO_TARGET=1` — gaps:

- No epoch refreeze after promotion
- Journal lacks `graduation_files[]`, `graduation_message`
- No optional post-copy pytest verify + rollback
- No phase journal at epoch boundary

---

## Reading list (read before coding)

### Charter & gaps

| Path | Focus |
|------|-------|
| `Agentic_campaign/FIX_4.md` | §5 Segment B, §2.2 target flow, §9.1 gating R34 |
| `daedalus/MISSING.JSON` | X-001, X-002 |
| `daedalus/RUN_GAPS.JSON` | RG-F001 |

### Code anchors

| Path | Focus |
|------|-------|
| `daedalus/orchestrator/epochs/e5_assimilate.py` | `assimilate()` ordering lines 46–76, 184 |
| `daedalus/orchestrator/campaign.py` | Epoch complete hook, `_record_op_round` |
| `daedalus/bridge/graduation.py` | Consumes 4A `ToolResult.data` (read-only unless coordinating) |
| `daedalus/verification/live/_common.py` | `pin_baseline` wrapper |
| `daedalus/frozen/refreeze.py` | Read-only — authority for manifest semantics |
| `daedalus/config/daedalus_config.py` | New env vars |

### Institutional & OSS

- **AlphaEvolve** (arXiv:2506.13131) — register to eval tree after evaluator monopoly
- **DGM** (arXiv:2505.22954) — benchmark replay on promoted codebase
- **Gödel Machine** — verify (pytest) before treating promotion as committed
- [jennyzzt/dgm](https://github.com/jennyzzt/dgm) — self-modification apply loop

---

## Owned files (exclusive write)

| File | Action |
|------|--------|
| `daedalus/orchestrator/epochs/e5_assimilate.py` | Hook ordering, full journal payload, optional pytest verify |
| `daedalus/orchestrator/campaign.py` | `_on_op_epoch_complete`, promotion tracking, phase journal |
| `daedalus/config/daedalus_config.py` | `DAEDALUS_REFREEZE_AFTER_EPOCH`, `DAEDALUS_GRADUATE_VERIFY_PYTEST`, `DAEDALUS_GRADUATE_MODE` stub |

---

## Forbidden overlaps

- Do **not** reimplement graduation copy logic (FIX_4-A)
- Do **not** modify `frozen/refreeze.py` core semantics
- Do **not** add `--graduate` CLI (FIX_4-C)
- Do **not** bypass R51/R34 guards in E5

---

## Implementation checklist

### E5 hook ordering (preserve + extend)

```text
ACCEPT path:
  1. Assert R51 + R34 in transcript (existing)
  2. graduate_branch_to_target (if flag + branch_dir)
  3. Optional: target pytest if DAEDALUS_GRADUATE_VERIFY_PYTEST=1; rollback on fail
  4. journal.record with full graduation payload from 4A
  5. emit_from_accept (parallel path — 4D documents)
  6. archive, pareto, vault, lessons, GNN
```

### Epoch refreeze — `_on_op_epoch_complete`

Trigger when:

- `DAEDALUS_GRADUATE_TO_TARGET=1`
- `DAEDALUS_REFREEZE_AFTER_EPOCH=1` (default `1` when graduate on)
- ≥1 journal record in epoch with `promoted_to_target=true`

```python
from verification.live._common import pin_baseline
pin_baseline(target_path, slug=target_slug)
log_stage("refreeze_epoch", f"epoch={epoch_index} slug={target_slug}")
```

### Phase journal entry

```json
{
  "phase": "epoch_complete",
  "epoch": 1,
  "promotions": 2,
  "refreeze": true,
  "notes": "generated/ synced from accepts; frozen repinned"
}
```

### Config additions

| Variable | Default |
|----------|---------|
| `DAEDALUS_REFREEZE_AFTER_EPOCH` | `1` when graduate on, else `0` |
| `DAEDALUS_GRADUATE_VERIFY_PYTEST` | `0` |
| `DAEDALUS_GRADUATE_MODE` | `per_accept` (`epoch_champion` deferred) |

### E0 alignment verify

After refreeze, epoch N+1 `run_e0` must ground on updated baseline hashes.

---

## Verification suite (must all pass)

### Primary gate

```bash
cd daedalus
python verification/run_all_daedalus_verifications.py
```

### Agent-specific checks (4E may formalize)

| Test | Expected |
|------|----------|
| E5 assimilate mock | `extra["promoted_to_target"]` + `graduation_files` non-empty |
| Source inspect | Graduation only when `ev.accepted and ev.branch_dir` |
| Refreeze trigger | `log_stage("refreeze_epoch"` when promotions > 0 |
| Pytest verify flag | Rollback copies on pytest failure when flag=1 |
| Regression | R51/R34 guard still enforced |

---

## Done-when criteria

- [ ] E5 journal carries full graduation payload from 4A result
- [ ] Epoch complete triggers `pin_baseline` when configured
- [ ] Phase journal documents refreeze
- [ ] No graduation before accept + gate transcript
- [ ] Verifiers exit 0

---

## Cursor spin-up block

```
You are AGENT 4B implementing FIX_4 Segment B from Agentic_campaign/FIX_4.md.

Read: Fix_4_prompts/AGENT_4B_E5_REFREEZE_HOOK.md, FIX_4.md §5,
e5_assimilate.py, campaign.py, pin_baseline, refreeze.py (read-only).

Prerequisite: FIX_4-A merged (GraduationResult schema in ToolResult.data).

Constraints:
- Graduation only after R51+R34 on ACCEPT — no bypass
- Call pin_baseline only — do not edit refreeze.py core
- Exit 0 on verification/run_all_daedalus_verifications.py

Deliver: E5 journal payload + epoch refreeze hook + config env vars.
```
