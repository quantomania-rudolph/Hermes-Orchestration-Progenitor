# AGENT 4A — graduation.py Hardening + RSI_scaled Mirror + Journal Fields

---

## Persona

You are an **advanced systems engineer** who builds promotion pipelines with cryptographic audit trails and fail-closed copy semantics. DGM-style in-place evolution requires that accepted sandbox branches merge into the live target tree with byte-verified parity — not optimistic journal flags. You never set `promoted_to_target: true` unless files actually landed on disk with matching hashes.

---

## Core objective

**Harden `graduate_branch_to_target`** with explicit file lists, SHA256 hashes, structured errors, `log_stage` observability, and RSI_scaled mirror parity. Enrich `ToolResult.data` so E5 can write truthful journal fields. Close **X-001** at the copy layer.

---

## Problem statement

Partial wiring exists but production gaps remain:

| Gap | Evidence |
|-----|----------|
| No content hashes in journal | RG-B002 — archive fills; `generated/` static |
| RSI_scaled mirror untested | Only `HERMES_GENERATED_DIR` patched in `_verify_graduation_hook()` |
| No `log_stage` on graduation | Operators cannot see copy events in campaign stdout |
| Quarantine pollution risk | Branch may contain `daedalus_quarantine/` paths |
| Partial copy sets promoted true | Fail-closed required |

**Live evidence (RUN_GAPS RG-B002 / RG-F001):**

```
E5 assimilate → archive.json + journal → proposal_queue
generated/simple_rsi_strategy/ never updated
pin_baseline copies generated/ → frozen/; mutations in sandbox/branches/cand_*
```

---

## Reading list (read before coding)

### Charter & gaps

| Path | Focus |
|------|-------|
| `Agentic_campaign/FIX_4.md` | §4 Segment A, §3.1 graduation audit, invariants I-1–I-7 |
| `daedalus/MISSING.JSON` | X-001 critical |
| `daedalus/RUN_GAPS.JSON` | RG-B002, RG-F001 |

### Code anchors

| Path | Focus |
|------|-------|
| `daedalus/bridge/graduation.py` | `graduate_branch_to_target`, `_graduation_roots`, `editable_target_files` |
| `daedalus/orchestrator/epochs/e5_assimilate.py` | Read-only — consumes graduation result (4B wires journal) |
| `daedalus/verification/verify_proposal_engine.py` | `_verify_graduation_hook()` (~line 355) |
| `daedalus/config/daedalus_config.py` | `HERMES_GENERATED_DIR`, `DAEDALUS_ROOT` |
| `daedalus/RSI_scaled/simple_rsi_strategy/` | Mirror destination |

### Institutional & OSS

- **DGM** (arXiv:2505.22954) — agent patches own Python codebase; benchmark replay promotes
- **AlphaEvolve** (arXiv:2506.13131) — register program to live eval tree after evaluator monopoly
- **QuantEvolve** (arXiv:2510.18569) — only deterministic evaluator promotes
- **Gödel Machine** — verify before commit; hashes enable audit
- [jennyzzt/dgm](https://github.com/jennyzzt/dgm) — in-place edit patterns

---

## Owned files (exclusive write)

| File | Action |
|------|--------|
| `daedalus/bridge/graduation.py` | A.1–A.6: hashes, logging, mirror verify, error table |
| `daedalus/verification/verify_proposal_engine.py` | Extend `_verify_graduation_hook()` — RSI_scaled mirror assertion |

---

## Forbidden overlaps

- Do **not** modify E5 hook ordering or epoch refreeze (FIX_4-B)
- Do **not** modify `campaign.py` (FIX_4-B/C)
- Do **not** modify `proposal_queue.py` (FIX_4-D)
- Do **not** add graduation bypass before R34 (gating monopoly)

---

## Implementation checklist

### A.1 — `ToolResult.data` schema

| Key | Type | Description |
|-----|------|-------------|
| `promoted_to_target` | bool | True iff ≥1 file copied successfully |
| `candidate_id` | str | Source candidate |
| `target_slug` | str | Destination slug |
| `files` | list[str] | Absolute paths written |
| `file_hashes` | dict[str, str] | rel_path → sha256 |
| `dest_roots` | list[str] | Roots touched |
| `skipped` | list[str] | Not copied (forbidden/missing) |
| `mirror_ok` | bool | RSI_scaled copies match generated |

### A.2 — Copy rules

```text
PRECONDITIONS: branch_dir exists; editable_target_files non-empty; slug [a-z0-9_]+
SKIP: daedalus_quarantine/, tests/, __pycache__/, gate/, frozen/
COPY: copy2 to each dest_root / rel (additive merge v1 — no deletes)
POST: byte-compare mirror; sha256 per file
```

### A.3 — Logging via `log_stage`

```text
graduation:start candidate=cand_xxx slug=simple_rsi_strategy
graduation:copy file=data_loader.py dest=generated/...
graduation:done promoted=true files=3 mirror_ok=true
graduation:skip reason=no_editable_files
```

### A.4 — Journal fields (schema for 4B to write)

```json
{
  "promoted_to_target": true,
  "graduation_files": ["data_loader.py", "signal_model.py"],
  "graduation_dest_roots": ["..."],
  "graduation_file_hashes": {"data_loader.py": "abc123..."},
  "graduation_message": "graduated cand_xxx → simple_rsi_strategy (6 file copies)"
}
```

### A.5 — RSI_scaled mirror

- If `RSI_scaled/` exists but `RSI_scaled/<slug>/` missing → `mkdir` mirror root
- Unit test: temp RSI_scaled parent; assert both trees updated; `filecmp.cmp`

### A.6 — Error handling table

| Condition | `ok` | `promoted_to_target` |
|-----------|------|----------------------|
| Missing branch_dir | False | False |
| No editable files | False | False |
| Partial copy failure | False | False |
| All copies OK | True | True |

---

## Verification suite (must all pass)

### Primary gate

```bash
cd daedalus
python verification/run_all_daedalus_verifications.py
python verification/verify_proposal_engine.py
```

### Agent-specific checks

| Test | Expected |
|------|----------|
| `_verify_graduation_hook()` | `promoted_to_target`, bytes match |
| RSI_scaled mirror test | Both roots updated; `mirror_ok=true` |
| Hash keys | `file_hashes` non-empty for each copied rel |
| Error paths | No editable files → `promoted_to_target=false` |
| Quarantine skip | `daedalus_quarantine/` not in `files` |

### Manual smoke

```python
from bridge.graduation import graduate_branch_to_target
# temp branch with signal_model.py modification → assert hash in result.data
```

---

## Done-when criteria

- [ ] `graduate_branch_to_target` returns `file_hashes` for every copied file
- [ ] RSI_scaled mirror test passes in verifier
- [ ] `log_stage` lines appear when graduation runs
- [ ] Partial failure never sets `promoted_to_target: true`
- [ ] `run_all_daedalus_verifications.py` exit 0

---

## Cursor spin-up block

```
You are AGENT 4A implementing FIX_4 Segment A from Agentic_campaign/FIX_4.md.

Read: Fix_4_prompts/AGENT_4A_GRADUATION_HARDENING.md, FIX_4.md §4,
bridge/graduation.py, verify_proposal_engine._verify_graduation_hook,
RUN_GAPS.JSON RG-B002.

Wave 1 blocking agent — merge before 4B.

Constraints:
- Fail-closed promotion; journal schema in ToolResult.data for 4B
- Default DAEDALUS_GRADUATE_TO_TARGET remains 0
- Exit 0 on verification/run_all_daedalus_verifications.py
- Do not modify e5_assimilate hook ordering (4B)

Deliver: hardened graduation.py + mirror test + log_stage + hash journal schema.
```
