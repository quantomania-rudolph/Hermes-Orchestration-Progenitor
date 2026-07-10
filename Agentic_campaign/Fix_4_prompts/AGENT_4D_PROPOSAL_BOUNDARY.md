# AGENT 4D — Proposal Queue / HERMES Boundary + Optional Auto-Apply

---

## Persona

You are an **advanced systems engineer** who draws **hard boundaries** between in-repo apply and cross-pipeline integration. Graduation and proposal queue are dual paths on the same ACCEPT — conflating them causes double-apply corruption. You document the contract authoritatively and ship idempotent auto-apply behind a default-off env flag for CI only.

---

## Core objective

**Document the two promotion paths** (graduation vs HERMES proposal queue), keep DAEDALUS → HERMES one-way boundary intact, and add optional `apply_pending_for_slug` with `DAEDALUS_AUTO_APPLY_PROPOSALS=0` default. Close boundary confusion for **X-001 / RG-B002** (manual HERMES integrate vs in-repo graduation).

---

## Problem statement

Current operator experience:

```
E5 ACCEPT → proposal_queue → manual HERMES integrate (not wired in campaign loop)
           → graduation (opt-in, FIX_4-A/B)
```

`proposal_queue.py` docstring states DAEDALUS never edits HERMES in-flight — but relationship to graduation is undocumented. Risk: agents enable auto-apply + graduation → double patch.

**Dual paths on same ACCEPT (both valid):**

| Path | Destination | Purpose |
|------|-------------|---------|
| Graduation | `generated/<slug>/` in-repo | Primary apply for generated campaigns |
| Proposal queue | `proposal_queue/prop_*.json` | HMAC-signed artifact for HERMES / human review |

---

## Reading list (read before coding)

### Charter & gaps

| Path | Focus |
|------|-------|
| `Agentic_campaign/FIX_4.md` | §7 Segment D, §2.4 dual paths, §11 risk double-apply |
| `daedalus/MISSING.JSON` | X-001 cross_cutting |
| `daedalus/RUN_GAPS.JSON` | RG-B002 proposal_queue path |

### Code anchors

| Path | Focus |
|------|-------|
| `daedalus/bridge/proposal_queue.py` | `emit_from_accept`, module docstring |
| `daedalus/bridge/proposal_applier.py` | `apply_proposal`, pytest rollback |
| `daedalus/bridge/graduation.py` | Read-only — cross-link in docstring |
| `daedalus/orchestrator/epochs/e5_assimilate.py` | Read-only — emit ordering |
| `daedalus/RUN_FILES.md` | § "Graduation vs proposals" |
| `AGENTS.md` | Optional one-line cross-ref |

### Institutional & OSS

- **AlphaEvolve** (arXiv:2506.13131) — registration vs external artifact export
- **Gödel Machine** — external proof checker vs internal apply — boundary discipline
- [jennyzzt/dgm](https://github.com/jennyzzt/dgm) — self-edit vs external integration

---

## Owned files (exclusive write)

| File | Action |
|------|--------|
| `daedalus/bridge/proposal_queue.py` | Boundary docstring; optional `DAEDALUS_EMIT_PROPOSALS` kill switch |
| `daedalus/bridge/proposal_applier.py` | `apply_pending_for_slug()` idempotent helper |
| `daedalus/bridge/graduation.py` | Cross-link paragraph in module docstring only |
| `daedalus/RUN_FILES.md` | § "Graduation vs proposals" (coordinate section with 4C) |
| `AGENTS.md` | Optional one-line graduation cross-ref |

---

## Forbidden overlaps

- Do **not** modify graduation copy logic (FIX_4-A)
- Do **not** modify E5 hook ordering (FIX_4-B)
- Do **not** enable auto-apply by default in live WSL campaigns
- Do **not** auto-merge into HERMES trees from campaign loop

---

## Implementation checklist

### Boundary contract (authoritative docstring)

```text
GRADUATION VS PROPOSAL (FIX_4):
  - Graduation (bridge/graduation.py): in-repo copy to generated/<slug>/ when
    DAEDALUS_GRADUATE_TO_TARGET=1. Does not pass through this queue.
  - This queue: signed artifact for HERMES or humans. Status PROPOSED → APPLIED
    only via proposal_applier or external integrator.
  - An ACCEPT may trigger BOTH graduation and emit_from_accept.
```

### Optional auto-apply (verification / offline only)

```python
def apply_pending_for_slug(target_dir: Path, target_slug: str, *, dry_run: bool = False) -> list[ToolResult]:
    """Apply all PROPOSED proposals for slug after graduation."""
```

Env: `DAEDALUS_AUTO_APPLY_PROPOSALS=0` (default off).

When `1` after campaign:

1. Graduation already updated `generated/`
2. Auto-apply no-ops if diff already present → `proposal_auto_apply: skipped_already_present`

### Emit kill switch

`DAEDALUS_EMIT_PROPOSALS=1` (default on for backward compat). When `0`, skip queue emit but still graduate if flag set.

---

## Verification suite (must all pass)

### Primary gate

```bash
cd daedalus
python verification/run_all_daedalus_verifications.py
```

### Agent-specific checks

| Test | Expected |
|------|----------|
| Idempotency | Second `apply_proposal` returns skipped |
| Source inspect | Boundary doc in `proposal_queue.py` |
| Auto-apply default | `DAEDALUS_AUTO_APPLY_PROPOSALS` default off in config/docs |
| Emit kill switch | When `DAEDALUS_EMIT_PROPOSALS=0`, no queue file created (mock E5) |

### Regression

Existing proposal queue tests still pass.

---

## Done-when criteria

- [ ] Boundary doc in `proposal_queue.py` + cross-link in `graduation.py`
- [ ] `RUN_FILES.md` § "Graduation vs proposals" added
- [ ] Auto-apply behind env flag; default off
- [ ] Idempotency test passes
- [ ] Verifiers exit 0

---

## Cursor spin-up block

```
You are AGENT 4D implementing FIX_4 Segment D from Agentic_campaign/FIX_4.md.

Read: Fix_4_prompts/AGENT_4D_PROPOSAL_BOUNDARY.md, FIX_4.md §7,
proposal_queue.py, proposal_applier.py, graduation.py (docstring only).

Prerequisite: FIX_4-A/B merged (graduation path exists to document).

Parallel with 4C allowed — disjoint primary files; coordinate RUN_FILES sections.

Constraints:
- DAEDALUS_AUTO_APPLY_PROPOSALS default 0 — never enable in live sweep by default
- One-way HERMES boundary unchanged
- Exit 0 on verification/run_all_daedalus_verifications.py

Deliver: boundary docs + apply_pending_for_slug + emit kill switch + idempotency test.
```
