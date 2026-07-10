# AGENT 3B — REFACTOR Double-Spawn IDLE_STALL Fix (P2-002 / RG-A001)

---

## Persona

You are an **advanced systems engineer** who profiles live Cursor orchestration like a distributed systems incident. You eliminate redundant 180s IDLE_STALL spawns, gate pre-review loops on compile-clean + work-complete paths, and journal sub-stage timings so operators see flash vs idle vs pre-gate. AlphaEvolve §2.6 async throughput starts with not burning 450s per REFACTOR round.

---

## Core objective

**Kill the REFACTOR double-spawn IDLE_STALL pattern** (403–494s E3) by skipping redundant rewrite fallback and pre-gate spawns when flash mutation succeeds with `work_hits > 0` and clean compile. Close **P2-002 / RG-A001**.

---

## Problem statement

Live log pattern from `run_gaps_simple_rsi_002`:

```
mutate:REFACTOR:flash  ~95–140s  (work_hits > 0 often)
spawn:claude           ~180s IDLE_STALL (out_bytes=0)
retry attempt2         ~99–118s
PreGateReview?         additional spawns
```

**Hypothesis chain (investigate in order):**

1. Pre-gate review spawns after successful flash mutation (`mutator.py` L309–335)
2. E8 rewrite fallback despite `work_hits>0` (guard at L165–166 should skip — verify race)
3. `discover_changed_files` empty until rescan (L212–222)
4. `ensure_before=True` on every pre-gate pass
5. Spawn label shows `spawn:claude` not resolved `model_id` (RG-A005 adjunct)

**Existing partial fix:** `cursor_cli.py` L274–284 work-complete idle when `work_product_hits > 0`.

---

## Reading list (read before coding)

### Charter & gaps

| Path | Focus |
|------|-------|
| `Agentic_campaign/FIX_3.md` | §5 Segment B, Appendix B spawn labels, Appendix D.2 |
| `daedalus/MISSING.JSON` | P2-002 high |
| `daedalus/RUN_GAPS.JSON` | RG-A001 timing evidence |

### Code anchors

| Path | Focus |
|------|-------|
| `daedalus/agents/mutator.py` | Primary spawn, rewrite fallback L165–166, rescan L212–222, pre-gate L309–335 |
| `daedalus/agents/pre_gate_review.py` | Loop spawns, `ensure_before` L107 |
| `daedalus/agents/cursor_cli.py` | IDLE_STALL vs work-complete idle L274–284 |
| `daedalus/agents/cursor_sdk.py` | Spawn logging, `model_id` propagation |
| `daedalus/config/daedalus_config.py` | New env var pattern |
| `daedalus/agents/mutator_diff.py` | E8 apply path coupling |

### Institutional & OSS

- **AlphaEvolve** (arXiv:2506.13131) — §2.6 minimize serial LLM stalls
- **Gödel Machine** — expensive proof/search only when cheap path fails
- [OpenEvolve](https://github.com/codelion/openevolve) — async eval pipeline patterns

---

## Owned files (exclusive write)

| File | Action |
|------|--------|
| `daedalus/agents/mutator.py` | B-1 compile probe before pre-gate; B-2 `rescan_ms`; B-3 rewrite gate |
| `daedalus/agents/pre_gate_review.py` | B-1 skip policy; B-4 `ensure_before=False` pass ≥2; D-3 heartbeat |
| `daedalus/agents/cursor_sdk.py` | B-5 log resolved `model_id` in spawn line |
| `daedalus/config/daedalus_config.py` | B-6 `DAEDALUS_SKIP_PREGATE_ON_WORK` default `1` |

---

## Forbidden overlaps

- Do **not** modify `bridge/diff_apply.py` (FIX_3-C — merge 3C first)
- Do **not** modify `prompt_sampler.py` (FIX_3-A)
- Do **not** own full `e3_timings` journal merge (FIX_3-D) — emit timings dict from mutator for D to merge

---

## Implementation checklist

1. **Pre-gate skip policy** — skip when:
   - `PRE_GATE_REVIEW_ENABLED=0`, OR
   - `work_hits > 0` AND zero compile errors on first `_compile_errors`, OR
   - `REFACTOR` + `DAEDALUS_SKIP_PREGATE_ON_WORK=1` (default `1`)

2. **Rewrite fallback gate** — require `work_hits==0` AND apply attempted:
   ```python
   if (context.diff_mode == "patch" and new_src == old_src and spawn_work_hits == 0):
   ```

3. **Rescan timing** — `rescan_ms` around `discover_changed_files` retry block.

4. **`e3_timings` partial dict** from mutator (for 3D merge):
   - `spawn_ms`, `flash_ms`, `rescan_ms`, `apply_ms`, `rewrite_spawn_ms`, `pre_gate_ms`, `pre_gate_spawns`

5. **Stdout:**
   ```
   [cursor] done ... work_hits=N
   [daedalus] E3_mutate:REFACTOR done (Xs) sub={spawn_ms,rescan_ms,pre_gate_ms}
   ```

6. **Config:** `DAEDALUS_SKIP_PREGATE_ON_WORK=1` in `daedalus_config.py`.

---

## Verification suite (must all pass)

### Primary gates

```bash
cd daedalus
python verification/run_all_daedalus_verifications.py
python verification/verify_mutator_context.py
```

### Agent-specific checks

| Test | Expected |
|------|----------|
| Source inspect | `DAEDALUS_SKIP_PREGATE_ON_WORK` referenced in mutator |
| Simulated REFACTOR path | `pre_gate_spawns == 0` when compile clean + work_hits > 0 |
| Timing dict | `rewrite_spawn_ms == 0` when `work_hits > 0` |
| Regression | Pre-gate still runs when compile errors exist |
| Wall time smoke | REFACTOR on `data_loader.py` smoke < 200s (no 180s idle) — manual/live |

### Safety

Skipping pre-gate must not bypass R22 — compile probe before skip.

---

## Done-when criteria

- [ ] Single primary mutate spawn when flash succeeds with changed files
- [ ] `DAEDALUS_SKIP_PREGATE_ON_WORK` default `1`; env documented
- [ ] `e3_timings` keys emitted from mutator (3D merges to journal)
- [ ] No regression on compile-error paths
- [ ] Verifiers exit 0

---

## Cursor spin-up block

```
You are AGENT 3B implementing FIX_3 Segment B from Agentic_campaign/FIX_3.md.

Read: Fix_3_prompts/AGENT_3B_REFACTOR_IDLE_STALL.md, FIX_3.md §5,
mutator.py, pre_gate_review.py, cursor_cli.py, cursor_sdk.py,
RUN_GAPS.JSON RG-A001.

Prerequisite: FIX_3-C merged (fuzzy apply reduces rewrite fallback triggers).

Constraints:
- Skip pre-gate only with compile probe — R22 still catches errors
- Exit 0 on verification/run_all_daedalus_verifications.py + verify_mutator_context.py
- Do not modify prompt_sampler or diff_apply

Deliver: pre-gate skip policy + rescan_ms + rewrite gate + DAEDALUS_SKIP_PREGATE_ON_WORK + spawn logging.
```
