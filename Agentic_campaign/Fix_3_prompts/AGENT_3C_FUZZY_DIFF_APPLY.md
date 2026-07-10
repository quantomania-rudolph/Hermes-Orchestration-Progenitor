# AGENT 3C — Fuzzy SEARCH/REPLACE & Diff Apply (P2-003)

---

## Persona

You are an **advanced systems engineer** who builds **fail-closed, ambiguity-rejecting** diff application pipelines. AlphaEvolve §2.3 expects robust SEARCH/REPLACE application — exact substring match is insufficient when LLMs drift whitespace, indent, or trailing newlines. You implement tiered fuzzy matching without silent file corruption and record apply mode in transcripts for audit.

---

## Core objective

**Add fuzzy SEARCH/REPLACE and unified-diff hunk matching** to `bridge/diff_apply.py` so E8 patch mode succeeds without triggering expensive rewrite fallback spawns. Close **P2-003** and decouple apply failures from **RG-A001** IDLE_STALL chain.

---

## Problem statement

Current `bridge/diff_apply.py`:

- `apply_search_replace`: exact substring — fails on whitespace/indent drift
- `apply_unified_diff`: strict line equality — fails on missing trailing newline or hunk shift

Failure → E8 rewrite fallback → extra Cursor spawn (403–494s REFACTOR rounds).

**Apply order (preserve):** SEARCH/REPLACE first, then unified diff (`apply_diff` lines 111–122).

---

## Reading list (read before coding)

### Charter & gaps

| Path | Focus |
|------|-------|
| `Agentic_campaign/FIX_3.md` | §6 Segment C, Appendix D.4, safety constraints |
| `daedalus/MISSING.JSON` | P2-003 medium |
| `daedalus/RUN_GAPS.JSON` | RG-A001 coupling via rewrite fallback |

### Code anchors

| Path | Focus |
|------|-------|
| `daedalus/bridge/diff_apply.py` | `apply_search_replace`, `apply_unified_diff`, `apply_diff` |
| `daedalus/agents/mutator_diff.py` | `extract_search_replace_blocks`, `PatchResult.transcript` |
| `daedalus/agents/mutator.py` | E8 rewrite fallback trigger (read-only) |
| `daedalus/verification/verify_mutator_context.py` | P2-003 baseline strict apply |
| `daedalus/verification/verify_proposal_apply.py` | Existing diff apply tests |

### Institutional & OSS

- **AlphaEvolve** (arXiv:2506.13131) — §2.3 creative generation; SEARCH/REPLACE fences
- **QuantEvolve** (arXiv:2510.18569) — patches must apply to tradable strategy code reliably
- [OpenEvolve](https://github.com/codelion/openevolve) — diff application patterns

---

## Owned files (exclusive write)

| File | Action |
|------|--------|
| `daedalus/bridge/diff_apply.py` | C-1 fuzzy SEARCH; C-2 wire in `apply_diff`; C-3 unified fuzzy |
| `daedalus/agents/mutator_diff.py` | C-4 extract blocks from transcript; transcript `mode` field |
| `daedalus/tests/test_diff_apply_fuzzy.py` | **NEW** — C-5 golden tests |

---

## Forbidden overlaps

- Do **not** modify `mutator.py` pre-gate logic (FIX_3-B)
- Do **not** modify gate modules (R18 boundary)
- Do **not** relax fail-closed on ambiguous matches

---

## Implementation checklist

1. **`apply_search_replace_fuzzy(original, blocks) -> (str|None, tier)`** with tiers:
   - Tier 0: exact (current)
   - Tier 1: strip trailing whitespace per line
   - Tier 2: normalize indentation (dedent to minimum common indent)
   - Tier 3: sliding window + `difflib.SequenceMatcher` ratio ≥ 0.92 on normalized lines

2. **Wire fuzzy path** in `apply_diff` before unified diff.

3. **`apply_unified_diff_fuzzy`** — `rstrip` normalization; ±2 line drift in hunk anchor search.

4. **`mutator_diff.py`** — extract SEARCH/REPLACE from transcript (not only unified); set `PatchResult.transcript.mode`:
   - `search_replace_fuzzy` | `unified_fuzzy` | existing modes

5. **Golden tests** — indent drift, missing newline, minor SEARCH typo (10 variants).

### Safety constraints (mandatory)

- Single-file only — no cross-boundary apply
- Multiple fuzzy matches (count > 1) → reject hunk, fail closed to rewrite
- Malformed blocks → `None`, no silent corruption

---

## Verification suite (must all pass)

### Primary gates

```bash
cd daedalus
python verification/run_all_daedalus_verifications.py
python verification/verify_mutator_context.py
python -m pytest daedalus/tests/test_diff_apply_fuzzy.py -q
```

### Agent-specific checks

| Test | Expected |
|------|----------|
| Golden 10/10 | Fuzzy variants apply without rewrite |
| Ambiguity | Two matches → `None` |
| Malformed blocks | `None`, file unchanged |
| `verify_mutator_context` | Tier-1 whitespace case passes |
| Transcript audit | `mode: search_replace_fuzzy` in PatchResult |

### Regression

Existing strict apply cases in `verify_proposal_apply.py` and `verify_mutator_context.py` still pass.

---

## Done-when criteria

- [ ] Fuzzy tiers 0–3 implemented with fail-closed ambiguity rejection
- [ ] 10/10 golden tests pass
- [ ] `apply_diff` records mode in transcript
- [ ] `run_all_daedalus_verifications.py` exit 0

---

## Cursor spin-up block

```
You are AGENT 3C implementing FIX_3 Segment C from Agentic_campaign/FIX_3.md.

Read: Fix_3_prompts/AGENT_3C_FUZZY_DIFF_APPLY.md, FIX_3.md §6,
bridge/diff_apply.py, mutator_diff.py, verify_mutator_context P2-003 baseline.

Wave 1 blocking agent — merge before 3B.

Constraints:
- Fail-closed on ambiguous fuzzy matches; single-file only
- Exit 0 on verification/run_all_daedalus_verifications.py + verify_mutator_context.py
- Do not modify mutator.py or gate modules

Deliver: apply_search_replace_fuzzy + unified fuzzy + golden tests + transcript mode field.
```