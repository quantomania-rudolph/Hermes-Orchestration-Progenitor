# AGENT 3E — verify_mutator_context Extensions & Integration Smoke

---

## Persona

You are an **advanced systems engineer** who closes FIX_3 with **falsifiable offline proof** — not live Cursor hope. You extend `verify_mutator_context.py` with checks E-1 through E-7, register smoke scripts, and ensure aggregate verification exit 0 before any campaign declares P2 mitigated. You write verification and fixtures only; production bugs get filed to RUN_GAPS, not patched in verifier hacks.

---

## Core objective

**Integrate all FIX_3 segments into the verification harness**: `section_nonempty`, fuzzy apply tiers, pre-gate skip references, E3 telemetry source inspects, and golden context→apply pipeline. Close the FIX_3 definition-of-done verification layer.

---

## Problem statement

`verify_mutator_context.py` already covers rich prompt sections, last-accept fallback (mocked), E8 rewrite transcript, strict SEARCH/REPLACE, and `work_hits` wiring — but **missing** FIX_3 deliverables:

| ID | Gap |
|----|-----|
| E-1 | `section_nonempty` in manifest |
| E-2 | Fuzzy SEARCH/REPLACE tier-1 whitespace |
| E-3 | `apply_diff` returns `search_replace_fuzzy` mode |
| E-4 | `e3_timings` keys in `e3_e4_verify` stats merge |
| E-5 | `DAEDALUS_SKIP_PREGATE_ON_WORK` in mutator source |
| E-6 | `log_stage("E3_context"` in e3_e4 |
| E-7 | Integration: `build_mutation_context` → `apply_patch_or_rewrite` golden |

No single offline script proves RG-C003 and RG-A001 cannot recur silently.

---

## Reading list (read before coding)

### Charter & gaps

| Path | Focus |
|------|-------|
| `Agentic_campaign/FIX_3.md` | §8 Segment E, §11 definition of done, §16 operator runbook |
| `daedalus/MISSING.JSON` | phase_2 full list |
| `daedalus/RUN_GAPS.JSON` | RG-A001, RG-C003 — encode as regression assertions |

### Code & verifier patterns

| Path | Focus |
|------|-------|
| `daedalus/verification/verify_mutator_context.py` | Existing P2-001–P2-006 checks, `check()` style |
| `daedalus/verification/run_all_daedalus_verifications.py` | Registration pattern |
| `daedalus/verification/verify_proposal_apply.py` | Diff apply patterns |
| `daedalus/search/prompt_sampler.py` | Manifest schema target |
| `daedalus/bridge/diff_apply.py` | Fuzzy apply (3C) |
| `daedalus/agents/mutator.py` | Pre-gate skip (3B) |
| `daedalus/orchestrator/epochs/e3_e4_verify.py` | Telemetry (3D) |

### Prior agent deliverables (consume)

| Agent | Artifact to verify |
|-------|-------------------|
| 3A | `section_nonempty`, `E3_context` log, inspiration fallback |
| 3B | `DAEDALUS_SKIP_PREGATE_ON_WORK`, rewrite guard |
| 3C | Fuzzy tiers, golden tests, transcript mode |
| 3D | `e3_timings` merge, `E3_breakdown` |

### Institutional

- **AlphaEvolve** — offline eval contract mirrors production prompt/apply path
- **DGM** — archive conditioning must appear in verification mocks

---

## Owned files (exclusive write)

| File | Action |
|------|--------|
| `daedalus/verification/verify_mutator_context.py` | E-1 through E-7 extensions |
| `daedalus/verification/smoke_e3_context_throughput.py` | **NEW** — optional CI adjunct |
| `daedalus/verification/run_all_daedalus_verifications.py` | Register smoke if added |
| `daedalus/verification/fixtures/e3/` | **NEW** optional — transcript snippets, journal seed |

---

## Forbidden overlaps

- **No production refactors** except test fixtures
- Do not re-implement 3A–3D logic to make tests pass — file RUN_GAPS blockers instead

---

## Implementation checklist

### E-1 through E-7 checks

| ID | Check | Method |
|----|-------|--------|
| E-1 | `section_nonempty` in manifest | Unit with mocked `PromptSampler.build()` |
| E-2 | Fuzzy tier-1 whitespace | `apply_search_replace_fuzzy` on indent drift fixture |
| E-3 | `search_replace_fuzzy` mode | `apply_diff` transcript/mode field |
| E-4 | `e3_timings` keys | Source inspect `e3_e4_verify.py` |
| E-5 | `DAEDALUS_SKIP_PREGATE_ON_WORK` | Source inspect `mutator.py` |
| E-6 | `E3_context` log | Source inspect `e3_e4_verify.py` |
| E-7 | Context → apply golden | Recorded transcript snippet offline |

### Smoke script `smoke_e3_context_throughput.py`

1. Offline baseline dir with `data_loader.py`
2. Seed journal with one ACCEPT diff
3. `build_mutation_context` → assert `inspiration_count >= 1`
4. `apply_diff` on malformed diff fixture → assert fuzzy recovery
5. Exit 0 in < 5s (no live Cursor)

### Gate commands (both required)

```bash
cd daedalus
python verification/run_all_daedalus_verifications.py
python verification/verify_mutator_context.py
```

### RUN_GAPS closeout template

After live validation, append:

```json
{"gap_refs": ["RG-A001"], "status": "mitigated_fix_3", "evidence": "E3_breakdown pre_gate=0s, duration<250s"}
{"gap_refs": ["RG-C003"], "status": "mitigated_fix_3", "evidence": "inspiration_ids non-empty round 2+"}
```

---

## Verification suite (must all pass)

### Aggregate output (CI-readable)

```
[OK] E-1: section_nonempty manifest keys present
[OK] E-2: fuzzy tier-1 whitespace apply
[OK] E-3: apply_diff search_replace_fuzzy mode
[OK] E-4: e3_timings in e3_e4_verify merge
[OK] E-5: DAEDALUS_SKIP_PREGATE_ON_WORK in mutator
[OK] E-6: E3_context log_stage in e3_e4
[OK] E-7: context to apply golden pipeline
[OK] smoke_e3_context_throughput exit 0
```

### Per-module debug

```bash
cd daedalus
python verification/verify_mutator_context.py
python verification/smoke_e3_context_throughput.py
```

---

## Done-when criteria

- [ ] All E-1–E-7 checks implemented and passing
- [ ] `run_all_daedalus_verifications.py` exit 0
- [ ] `verify_mutator_context.py` exit 0 standalone
- [ ] Smoke script < 5s, no network/Cursor
- [ ] FIX_3 definition of done §11 verification boxes satisfied

---

## Cursor spin-up block

```
You are AGENT 3E implementing FIX_3 Segment E from Agentic_campaign/FIX_3.md.

Read: Fix_3_prompts/AGENT_3E_VERIFY_INTEGRATION.md, FIX_3.md §8 §11,
verify_mutator_context.py, run_all_daedalus_verifications.py.

Prerequisite: FIX_3-A through 3-D merged (or rebase onto combined branch).

Constraints:
- Verification + fixtures ONLY — no production refactors
- Match existing check() style; no inline imports
- Both gate commands must exit 0

Deliver: E-1–E-7 checks + smoke_e3_context_throughput.py + RUN_GAPS mitigated entries template.
```
