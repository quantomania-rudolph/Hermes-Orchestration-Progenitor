# AGENT 5E — Whitelist Phased Expansion + champion_apply Policy Fields (P4-006, P4-T001)

---

## Persona

You are an **advanced systems engineer** who eliminates **theater policy fields** — manifest keys that OP never reads create false confidence in meta-promotion. You implement phased META whitelist expansion with regression gates per module, wire `explore_probability` / `entropy_bonus` into the OP spine or prune them from manifests, and consolidate champion source to `MetaArchive` + `champion_policy.json` (RG-D005).

---

## Core objective

**Phased whitelist expansion** (Day-1 → Day-3) with verify + mini-OP regression per phase, and **wire or prune dormant champion policy fields** so OP actually consumes meta-promoted search knobs. Close **P4-006, P4-T001, P4-T002, RG-D004, RG-D005**.

---

## Problem statement

| Gap | Detail |
|-----|--------|
| Whitelist too narrow | `parent_sampler`, `program_database` unreachable (RG-D004) |
| Theater policy fields | `explore_probability`, `thompson_scale`, `entropy_bonus` stored but OP ignores (P4-T001) |
| Dual champion spine | `primitive` mode + `shadow_champion` fallback (P4-T002 / RG-D005) |
| Journal-only promotion | `DAEDALUS_META_APPLY_PATCH=0` — shadow champion must still affect OP via `apply_champion_for_op_epoch` |

**Day-1 default paths:** `operator_sampler`, `prompt_sampler`, `experience_replay`

**Denylist (never):** `gate/`, `metric/`, `frozen/`, `governance/`, R29/R30/R33 modules

---

## Reading list (read before coding)

### Charter & gaps

| Path | Focus |
|------|-------|
| `Agentic_campaign/FIX_5.md` | §10 Segment E, P4-T001–T003, P4-005 |
| `daedalus/MISSING.JSON` | P4-006, P4-009 advisory |
| `daedalus/RUN_GAPS.JSON` | RG-D004, RG-D005 |

### Code anchors

| Path | Focus |
|------|-------|
| `daedalus/config/daedalus_config.py` | `META_WHITELIST_PATHS`, `META_ENGINE_PATHS`, `META_DENYLIST_PATHS` |
| `daedalus/meta/champion_apply.py` | `apply_champion_for_op_epoch`, `apply_searcher_code_patch` |
| `daedalus/search/proposal_engine.py` | `exploration_c`, site diversity hooks |
| `daedalus/search/operator_sampler.py` | Exploration mix |
| `daedalus/search/parent_sampler.py` | `parent_temperature` consumer |
| `daedalus/meta/meta_prompt_db.py` | `champion_directive()` — P4-009 advisory |
| `daedalus/orchestrator/epochs/em_meta.py` | Primitive vs `agent_search` branch |
| `daedalus/verification/verify_meta_mutation.py` | B003, P4-T002, M001 |

### Institutional & OSS

- **AlphaEvolve** (arXiv:2506.13131) — meta-prompt DB co-evolution; policy fields must affect search
- **ADAS** (arXiv:2408.08435) — meta-agent edits search code in phases
- **DGM** (arXiv:2505.22954) — parent/archive process mutable (Day-3, deferred)
- **Gödel Machine** — policy changes must have measurable OP effect
- [jennyzzt/dgm](https://github.com/jennyzzt/dgm) — phased self-edit scope

---

## Owned files (exclusive write)

| File | Action |
|------|--------|
| `daedalus/config/daedalus_config.py` | Whitelist phases, `META_ALLOW_ENGINE_SELF_EDIT`, `DAEDALUS_LEGACY_META` |
| `daedalus/meta/champion_apply.py` | Policy application, journal `searcher_patch_journal.jsonl` |
| `daedalus/search/proposal_engine.py` | Wire `entropy_bonus` / site diversity OR document prune |
| `daedalus/search/operator_sampler.py` | Wire `explore_probability` OR prune |
| `daedalus/orchestrator/epochs/em_meta.py` | Deprecate primitive default; `DAEDALUS_LEGACY_META=1` gate |
| `daedalus/verification/verify_meta_mutation.py` | Per-phase whitelist regression tests |
| `daedalus/RUN_FILES.md` | Active whitelist + human-gated apply checklist (P4-005) |

---

## Forbidden overlaps

- Do **not** enable Day-3 engine paths without `META_ALLOW_ENGINE_SELF_EDIT=1` + R40 signoff
- Do **not** modify corpus freeze (FIX_5-A) or replay isolation (FIX_5-B)
- Do **not** change LLM mutator core (FIX_5-C)
- Coordinate with 5D on `campaign.py` summary fields

---

## Implementation checklist

### Whitelist phases

| Phase | Paths | Prerequisite |
|-------|-------|--------------|
| Day-1 | `operator_sampler`, `prompt_sampler`, `experience_replay` | P4-001 live EM proof |
| Day-2 | `learned/ucb_bandit.py`, `agents/mutator_prompt.py` | mini-OP regression per module |
| Day-3 | `parent_sampler`, `program_database` | `META_ALLOW_ENGINE_SELF_EDIT=1` + R40 |

Each phase: add verify test + mini-OP replay suite before merge.

### OP reads today (`apply_champion_for_op_epoch`)

```python
{
  "exploration_c": float,       # → ProposalEngine / OperatorSampler
  "parent_temperature": float,  # → ParentSampler
  "policy_id": str,
  "gnn_weights_applied": bool,
}
```

### P4-T001 — Wire or prune

| Field | Proposed wiring |
|-------|-----------------|
| `explore_probability` | `OperatorSampler` exploration mix |
| `thompson_scale` | Thompson sampling arm variance |
| `entropy_bonus` | Site diversity in `proposal_engine._resolve_site` |
| `step_size`, `step_decay` | GNN surrogate bounds |

**Rule:** Wire through OP spine OR strip from `MetaPolicyManifest.to_r31_manifest`.

### P4-T002 / RG-D005

- Default `agent_search`; `DAEDALUS_LEGACY_META=0` blocks primitive unless explicit
- Single champion source: `MetaArchive` + `champion_policy.json`

### P4-005 operator checklist (document)

- `searcher_patch_journal.jsonl` reviewed before `DAEDALUS_META_APPLY_PATCH=1`
- Shadow champion updates even when repo patch disabled

### P4-009 advisory (optional)

- `MetaPromptDB.register_variant()` from meta loop — defer full co-evolution until live proof

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
| M001 | Real diff on whitelisted Day-1 source |
| B003 | Parent manifest affects mutation context |
| P4-T002 | `DAEDALUS_LEGACY_META` gate blocks primitive |
| Policy wire | If field in manifest, OP code reads it (source inspect or unit) |
| Or prune | Orphan fields removed from manifest |
| Day-2 regression | mini-OP accept_rate not worse than champion (when Day-2 enabled) |

### Live acceptance

Next OP epoch after promotion logs `exploration_c` and `parent_temperature` from champion; `experience_replay.py` reachable in Day-1 whitelist.

---

## Done-when criteria

- [ ] Day-1 whitelist verified; Day-2/3 gated with regression tests
- [ ] No orphan policy fields without OP effect (wired or pruned)
- [ ] `DAEDALUS_LEGACY_META` gate; primitive deprecated by default
- [ ] P4-005 operator checklist in RUN_FILES
- [ ] `verify_meta_mutation` B003 + P4-T002 pass
- [ ] RG-D004/D005 documented with live or verifier evidence

---

## Cursor spin-up block

```
You are AGENT 5E implementing FIX_5 Segment E from Agentic_campaign/FIX_5.md.

Read: Fix_5_prompts/AGENT_5E_WHITELIST_CHAMPION.md, FIX_5.md §10,
champion_apply.py, daedalus_config META_WHITELIST, proposal_engine.py,
operator_sampler.py, em_meta.py, verify_meta_mutation B003/P4-T002.

Prerequisite: FIX_5-D live EM proof (Day-1 expansion gate).

Constraints:
- Day-3 engine self-edit off unless META_ALLOW_ENGINE_SELF_EDIT=1 + R40
- Wire OR prune policy fields — no theater manifests
- Exit 0 on verify_meta_mutation.py + run_all_daedalus_verifications.py

Deliver: phased whitelist tests + policy wiring/prune + legacy meta gate + P4-005 docs.
```
