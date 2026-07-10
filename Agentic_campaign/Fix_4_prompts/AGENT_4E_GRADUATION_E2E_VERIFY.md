# AGENT 4E — E2E Graduation Verification + Integration Smoke

---

## Persona

You are an **advanced systems engineer** who proves **apply loops end-to-end** — not wiring inspect alone. You build `verify_graduation_e2e.py` with falsifiable tests: accept branch → `generated/simple_rsi_strategy` updated → pytest green → epoch refreeze → frozen matches generated. You write verification and fixtures only; production bugs get RUN_GAPS entries, not verifier hacks.

---

## Core objective

**Prove the full graduation path in the offline verification suite** — branch copy, E5 journal truth, RSI_scaled mirror parity, epoch refreeze, and post-graduation pytest. Wire into `run_all_daedalus_verifications.py`. Close FIX_4 definition-of-done for **X-001, X-002, RG-B002, RG-F001**.

---

## Problem statement

Existing coverage gaps:

| Gap | Detail |
|-----|--------|
| `_verify_graduation_hook()` only | Temp dir; no E5 integration; no RSI_scaled mirror (4A extends) |
| No epoch refreeze E2E | RG-F001 — frozen stale after graduation |
| No post-graduation pytest | Broken code could land in `generated/` |
| No real slug path test | `generated/simple_rsi_strategy/` not exercised |

**Minimum deliverable (charter):** One verified path from sandbox ACCEPT → `generated/<slug>/` (+ mirror) with journal truth and pytest green.

---

## Reading list (read before coding)

### Charter & gaps

| Path | Focus |
|------|-------|
| `Agentic_campaign/FIX_4.md` | §8 Segment E, §12 verification gate, §8.5 live smoke |
| `daedalus/MISSING.JSON` | X-001, X-002 |
| `daedalus/RUN_GAPS.JSON` | RG-B002, RG-F001 closure template |

### Code & verifier patterns

| Path | Focus |
|------|-------|
| `daedalus/verification/verify_proposal_engine.py` | `_verify_graduation_hook()` (~355) |
| `daedalus/verification/run_all_daedalus_verifications.py` | Registration pattern |
| `daedalus/verification/verify_cascade_accept_path.py` | Campaign forced-accept pattern (if exists) |
| `daedalus/bridge/graduation.py` | `editable_target_files` filter |
| `daedalus/orchestrator/epochs/e5_assimilate.py` | Journal record shape |
| `daedalus/orchestrator/campaign.py` | Epoch refreeze hook (4B) |

### Prior agent deliverables (consume)

| Agent | Artifact to verify |
|-------|-------------------|
| 4A | Hashes, mirror_ok, log_stage |
| 4B | E5 payload, refreeze_epoch |
| 4C | `--graduate`, promotion counts |
| 4D | Idempotent apply, boundary docs |

### Institutional

- **DGM** — promote only after eval replay passes
- **AlphaEvolve** — register program to eval tree with verification
- **QuantEvolve** — backtest/pytest gate before promotion counts

---

## Owned files (exclusive write)

| File | Action |
|------|--------|
| `daedalus/verification/verify_graduation_e2e.py` | **NEW** — Tests 1–4 below |
| `daedalus/verification/run_all_daedalus_verifications.py` | Register new verifier |
| `daedalus/verification/fixtures/graduation/` | **NEW** optional — branch + target fixtures |
| `daedalus/verification/verify_proposal_engine.py` | Mirror assertion extension only (if not done in 4A) |

---

## Forbidden overlaps

- **No production refactors** except test fixtures
- Do not bypass R34 in E2E tests — mock accept path, not gate monopoly

---

## Implementation checklist

### Test 1: `test_graduate_branch_updates_generated`

```text
SETUP: Temp HERMES_GENERATED_DIR with simple_rsi_strategy fixture
       Temp branch_dir with modified data_loader.py (LIMIT = 42)
       Patch DAEDALUS_GRADUATE_TO_TARGET = True
ACT:   graduate_branch_to_target(...)
ASSERT: generated/.../data_loader.py contains LIMIT = 42
        pytest in generated tree passes
```

### Test 2: `test_e5_assimilate_sets_journal_promoted`

```text
SETUP: Mock CandidateEvaluation accepted=True, branch_dir=temp branch
       Patch graduation → promoted_to_target=True, graduation_files non-empty
ACT:   assimilate(...)
ASSERT: last journal extra["promoted_to_target"] is True
        extra["graduation_files"] non-empty
```

### Test 3: `test_epoch_refreeze_after_promotion`

```text
SETUP: Campaign 1 epoch, 1 round, forced accept fixture
       DAEDALUS_GRADUATE_TO_TARGET=1, DAEDALUS_REFREEZE_AFTER_EPOCH=1
ACT:   camp.start(max_epochs=1, rounds=1)
ASSERT: frozen/baseline manifest matches generated hash
        log contains refreeze_epoch
```

### Test 4: `test_rsi_scaled_mirror_parity`

```text
Extend _verify_graduation_hook or standalone — copy to both roots, filecmp.cmp
```

### Wire into aggregate driver

Add `verify_graduation_e2e.py` after `verify_proposal_engine.py`.

### RUN_GAPS closeout template

```json
{
  "id": "RG-B002",
  "status": "closed_fix_4",
  "evidence": "journal cand_xxx promoted_to_target=true; generated/simple_rsi_strategy updated"
}
```

---

## Verification suite (must all pass)

### Gate commands (all required before FIX_4 closeout)

```bash
cd daedalus
python verification/run_all_daedalus_verifications.py
python verification/verify_graduation_e2e.py
python verification/verify_proposal_engine.py
```

Exit **0** on all three.

### CI-readable output

```
[OK] graduate_branch_updates_generated
[OK] e5_assimilate_sets_journal_promoted
[OK] epoch_refreeze_after_promotion
[OK] rsi_scaled_mirror_parity
[OK] editable_target_files excludes tests/
[OK] post_graduation_pytest when verify flag set
```

### Live smoke (operator, not CI)

```bash
export DAEDALUS_GRADUATE_TO_TARGET=1
python verification/live/run_all_generated_campaigns.py \
  --target simple_rsi_strategy --epochs 1 --rounds 3 --graduate
```

Expect: `promoted_to_target: true` in journal; `generated/` git diff non-empty; pytest green.

---

## Done-when criteria

- [ ] `verify_graduation_e2e.py` exit 0 offline
- [ ] `run_all_daedalus_verifications.py` exit 0
- [ ] E2E uses real `editable_target_files` filter (no tests/ copied)
- [ ] Post-graduation pytest invoked when `DAEDALUS_GRADUATE_VERIFY_PYTEST=1`
- [ ] FIX_4 §12 all verification boxes satisfied

---

## Cursor spin-up block

```
You are AGENT 4E implementing FIX_4 Segment E from Agentic_campaign/FIX_4.md.

Read: Fix_4_prompts/AGENT_4E_GRADUATION_E2E_VERIFY.md, FIX_4.md §8 §12,
verify_proposal_engine.py, run_all_daedalus_verifications.py.

Prerequisite: FIX_4-A through 4-D merged (or rebase onto combined branch).

Constraints:
- Verification + fixtures ONLY — no production refactors
- Match existing check() style; no inline imports
- All three gate commands must exit 0

Deliver: verify_graduation_e2e.py (4 tests) + driver registration + RUN_GAPS template.
```
