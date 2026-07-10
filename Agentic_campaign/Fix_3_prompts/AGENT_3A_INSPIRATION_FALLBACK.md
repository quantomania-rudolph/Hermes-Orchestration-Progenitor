# AGENT 3A — Inspiration Fallback When Archive Is Young (P2-001 / RG-C003)

---

## Persona

You are an **advanced systems engineer** who closes the cold-start conditioning gap in evolutionary LLM search. AlphaEvolve §2.2 assumes a populated program database — you guarantee **at least one conditioning exemplar** after the first ACCEPT so mutators are never fully unconditioned. You harden journal/archive timing races and make `prompt_manifest` auditable truth, not empty JSON theater.

---

## Core objective

**Guarantee minimum inspiration content in every E3 mutation context after the first non-bootstrap ACCEPT**, with manifest fields (`inspiration_source`, `section_nonempty`, `lineage_depth`) that reflect actual prompt sections. Close **P2-001 / RG-C003**.

---

## Problem statement

Live journals show empty manifests despite existing fallback code:

```
prompt_manifest: inspiration_ids=[], lesson_count=0, replay_failure_ids=[]
```

**Root causes:**

1. `sample_inspirations()` returns `[]` when `pop < 3` or `exclude_exploratory=True`
2. `last_accept_record()` returns `None` due to archive ingest lag vs journal
3. Parent is bootstrap — lineage chain does not attach to real `cand_*` (FIX_1 / RG-B003)
4. Parent exists but `parent.diff_text` empty — no pseudo-inspiration injected

**Existing code (do not re-implement):** `prompt_sampler.py` lines 76–86 last-accept fallback; `ProgramDatabase.last_accept_record()`; `MutationContext.is_empty()`.

---

## Reading list (read before coding)

### Charter & gaps

| Path | Focus |
|------|-------|
| `Agentic_campaign/FIX_3.md` | §4 Segment A, Appendix A manifest schema, Appendix D.1 |
| `daedalus/MISSING.JSON` | P2-001 critical |
| `daedalus/RUN_GAPS.JSON` | RG-C003, RG-B003 cross-ref |

### Code anchors

| Path | Focus |
|------|-------|
| `daedalus/search/prompt_sampler.py` | `build()`, inspiration fallback, manifest assembly |
| `daedalus/search/program_database.py` | `last_accept_record()` (~line 123), journal fallback |
| `daedalus/agents/mutation_context.py` | Adapter; `is_empty()`, brief-on-partial |
| `daedalus/orchestrator/epochs/e3_e4_verify.py` | E3 context build + logging (A-4) |
| `daedalus/search/parent_sampler.py` | Read-only — understand parent_id source (FIX_1) |

### Institutional & OSS

- **AlphaEvolve** (arXiv:2506.13131) — §2.2 parent + scores + inspirations + mutation history
- **DGM** (arXiv:2505.22954) — archive-conditioned parent diffs
- **Gödel Machine** — explicit utility/context in self-referential improvement loops
- [OpenEvolve](https://github.com/codelion/openevolve) — prompt sampling patterns
- [jennyzzt/dgm](https://github.com/jennyzzt/dgm) — parent selection + diff archive

---

## Owned files (exclusive write)

| File | Action |
|------|--------|
| `daedalus/search/program_database.py` | A-1: Harden `last_accept_record()` — journal `extra.diff_text` fallback |
| `daedalus/search/prompt_sampler.py` | A-2: Parent pseudo-inspiration; A-3: `section_nonempty` manifest |
| `daedalus/agents/mutation_context.py` | A-5: Brief with partial sections; no silent re-blind |
| `daedalus/orchestrator/epochs/e3_e4_verify.py` | A-4: `E3_context` stdout line via `log_stage` |

---

## Forbidden overlaps

- Do **not** modify `mutator.py` spawn logic (FIX_3-B)
- Do **not** modify `bridge/diff_apply.py` (FIX_3-C)
- Coordinate with **FIX_1** on `program_database.py` — merge FIX_1 parent-pool changes first if both touch same functions
- Do **not** strip FIX_2 `objective_summary` / `backtest_hook` from manifest

---

## Implementation checklist

1. **A-1 `last_accept_record()`** — tolerate archive ingest delay; backfill `diff_text` from journal `extra` for matching `candidate_id`.

2. **A-2 Parent pseudo-inspiration** — when inspirations empty but `parent.diff_text` non-empty:
   ```python
   inspirations = [parent_as_inspiration]
   inspiration_source = "parent_diff_only"
   ```

3. **A-3 `section_nonempty` manifest** — booleans for `{parent, inspirations, lessons, replay, subgraph}`.

4. **A-4 E3 stdout** after context build:
   ```
   [daedalus:HH:MM:SS] E3_context — inspirations=1 source=last_accept lessons=0 replay=2 lineage=0
   ```

5. **A-5 `mutation_context.py`** — brief with whatever sections exist; only fail on exception (B001 path).

6. **Manifest truth fields:** `inspiration_source`, `inspiration_count`, `inspiration_ids`, `lineage_depth`, `lineage_ids`.

---

## Verification suite (must all pass)

### Primary gates

```bash
cd daedalus
python verification/run_all_daedalus_verifications.py
python verification/verify_mutator_context.py
```

### Agent-specific checks (extend verifiers — or defer full E-* to 3E)

| Test | Expected |
|------|----------|
| Mocked empty archive + one journal ACCEPT | `inspiration_count >= 1`, `inspiration_source == last_accept` |
| Parent with diff, empty inspirations | `inspiration_source == parent_diff_only` |
| `section_nonempty` in manifest | All keys present; inspirations true when count ≥ 1 |
| Source inspect | `log_stage("E3_context"` or equivalent in `e3_e4_verify.py` |

### Live acceptance (post-merge)

Second OP round after first ACCEPT → journal `inspiration_ids` non-empty.

### Debt documentation

Document in code comment or RUN_GAPS: full lineage diversity requires FIX_1 (RG-B003).

---

## Done-when criteria

- [ ] Minimum inspiration guarantee after first non-bootstrap ACCEPT
- [ ] `section_nonempty` in manifest; E3_context log line emitted
- [ ] `verify_mutator_context.py` extended (or 3E completes extensions)
- [ ] `run_all_daedalus_verifications.py` exit 0
- [ ] FIX_1 dependency documented for full lineage acceptance

---

## Cursor spin-up block

```
You are AGENT 3A implementing FIX_3 Segment A from Agentic_campaign/FIX_3.md.

Read: Fix_3_prompts/AGENT_3A_INSPIRATION_FALLBACK.md, FIX_3.md §4,
prompt_sampler.py, program_database.last_accept_record, mutation_context.py,
RUN_GAPS.JSON RG-C003.

Prerequisite: FIX_3-D merged (e3_e4_verify log slot stable); FIX_1 preferred for lineage.

Constraints:
- No mutator spawn changes (3B) or diff_apply changes (3C)
- Exit 0 on verification/run_all_daedalus_verifications.py + verify_mutator_context.py
- Preserve FIX_2 objective_summary in mutation manifest

Deliver: hardened last_accept + parent_diff_only fallback + section_nonempty + E3_context log.
```
