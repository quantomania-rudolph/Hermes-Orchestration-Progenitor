# AGENT 1E — P1 Integration Verification & Live Acceptance Harness

**Wave:** 4 (after AGENT_1A–1D merged — verification-only agent)  
**Agent ID:** FIX_1-E  
**Charter reference:** `Agentic_campaign/FIX_1.md` §6 FIX_1-E, §7–§8  
**Gap IDs:** P1-001 live proof, RG-B003 acceptance, honesty rule enforcement  
**Estimated scope:** 2 files (1 new), ~150–250 LOC

---

## Persona

```text
You are FIX_1-E — an advanced systems engineer who distrusts green unit tests that don't reproduce production failures. You build regression fixtures that mirror run_gaps_simple_rsi_002 reward scales (bootstrap 2.313 vs accept 0.00037) and prove epoch-1 parent stability. You write acceptance scripts that parse campaign logs for forbidden patterns (boot_excl=True + parent=cold_start).

You do not modify production search/ modules except imports used by tests. You are the FIX_1 campaign's quality gate.
```

---

## Core objective

Extend **`verify_proposal_engine.py`** with run_002-scale regression tests and create **`verification/live/accept_fix1_parent_selection.py`** so FIX_1 fixes are **proven** beyond synthetic fixtures — closing the honesty gap documented in FIX_1 §1.1.

---

## Problem statement

### Honesty gap

`verify_proposal_engine.py` passes while live campaigns exhibit RG-B003 parent theater. Existing checks use synthetic `ProgramRecord` objects with comparable rewards — they never seed bootstrap at reward=2.313 and accept at 0.00037 in a temp archive, then call `propose()`.

### Required proof

1. Stale bootstrap reward migrates to R08 scale.
2. After first ACCEPT, `propose()` selects `cand_*` parent, not bootstrap.
3. Epoch 1 does not revert to bootstrap (run_002 failure mode).
4. Live log parser: ≥80% post-first-accept proposes use `cand_*` when `boot_excl=True`.

---

## Institutional reading

| Source | Section | Takeaway |
|--------|---------|----------|
| **DGM** | [arXiv:2505.22954](https://arxiv.org/abs/2505.22954) §C.2 | Empirical validation before archive promotion — tests must reflect archive state |
| **AlphaEvolve** | [arXiv:2506.13131](https://arxiv.org/abs/2506.13131) §2.4–2.5 | Evaluator monopoly + program DB — regression tests use same score path |
| **QuantEvolve** | [arXiv:2510.18569](https://arxiv.org/abs/2510.18569) | Backtest evaluator as ground truth — analogous to R08 gate reward in tests |

### OSS reference

- **jennyzzt/dgm** — https://github.com/jennyzzt/dgm — study how they test archive/parent selection if present.

---

## Required reading (repo)

| Path | Why |
|------|-----|
| `Agentic_campaign/FIX_1.md` | §7 Verification matrix, §8 Live acceptance |
| `daedalus/verification/verify_proposal_engine.py` | Full file — extend, don't break |
| `daedalus/verification/run_all_daedalus_verifications.py` | Register new live script if needed |
| `daedalus/RUN_GAPS.JSON` | RG-B003 patterns, phase_journal |
| `daedalus/verification/live/run_gaps_campaign_002.log` | Golden log for parser |
| `daedalus/search/proposal_engine.py` | propose() for integration |
| `daedalus/state/archive_manager.py` | Temp archive setup in tests |
| `daedalus/MISSING.JSON` | verification_honesty section |

---

## Owned files (exclusive write)

- `daedalus/verification/verify_proposal_engine.py`
- `daedalus/verification/live/accept_fix1_parent_selection.py` (**new**)
- Optionally register in `daedalus/verification/run_all_daedalus_verifications.py` — **only** if project convention adds live scripts to suite (prefer standalone + documented in FIX_1)

### Forbidden overlaps

- Do **not** modify `search/program_database.py`, `parent_sampler.py`, `proposal_engine.py`, or `campaign.py` (A–D complete first)
- If tests reveal bugs, file RUN_GAPS entry and send back to owning agent — do not patch production in 1E unless explicitly authorized

---

## Deliverables (exact)

### 1. `_verify_run002_reward_scale_regression()`

Setup:

- Temp archive with bootstrap `reward=2.313` (stale pre-fix scale)
- One ACCEPT `cand_test` with `reward=0.00037`
- Minimal `GroundingContext` + graph (config.py site cluster)
- Call `ensure_bootstrap_reward_normalized(ctx)` then `propose(seed=fixed)`

Assert:

- Bootstrap reward < 0.1 after migration
- `propose()` parent_id starts with `cand_` OR pool excludes bootstrap with `bootstrap_excluded=True`
- **Forbidden:** parent_id == `cold_start::baseline_champion` when real accept exists and boot_excl True

### 2. `_verify_epoch1_parent_not_bootstrap()`

Simulate:

1. Seed bootstrap
2. Register ACCEPT
3. Call `propose()` twice (epoch 0 round N, epoch 1 round 0 simulation)

Assert second propose parent ≠ bootstrap.

### 3. Extend `_verify_bootstrap_parent_selection`

- Call `ensure_bootstrap_reward_normalized` on stale archive fixture
- Assert pool exclusion + weight ordering at comparable rewards (existing checks ~296–309)

### 4. Source inspect checks

```python
check("ensure_bootstrap_reward_normalized" in inspect.getsource(propose_fn_or_engine),
      "proposal_engine calls bootstrap normalization")
check("bootstrap_excluded" in inspect.getsource(ProposalEngine.propose),
      "diag exports bootstrap_excluded")
```

### 5. Create `verification/live/accept_fix1_parent_selection.py`

CLI:

```bash
python verification/live/accept_fix1_parent_selection.py \
  --log verification/live/run_gaps_campaign_002.log \
  --min-cand-parent-fraction 0.8

python verification/live/accept_fix1_parent_selection.py \
  --dry-propose   # optional: run local propose loop without full campaign
```

**Parser logic:**

1. Find first line indicating ACCEPT with `cand_*` in journal or first `parent=cand_*` after bootstrap phase
2. For all subsequent `archive_propose` lines with `boot_excl=True`:
   - Count parent=cand_* vs parent=cold_start
3. **FAIL** if any line matches: `boot_excl=True` AND `parent=cold_start`
4. **PASS** if cand_* fraction ≥ `--min-cand-parent-fraction` (default 0.8)

Include bundled **golden log snippet** fixture for CI (post-fix synthetic log acceptable).

### 6. Document in FIX_1.md cross-reference

Add note in verify script docstring pointing to `Agentic_campaign/FIX_1.md` §8.5.

---

## Targeted verification suite

### Agent exit commands

```bash
cd daedalus
python verification/verify_proposal_engine.py
python verification/run_all_daedalus_verifications.py
python verification/live/accept_fix1_parent_selection.py --log verification/live/run_gaps_campaign_002.log --min-cand-parent-fraction 0.8
```

**Note:** Golden log from run_002 **should FAIL** parser until A–D land — keep `--expect-fail-legacy` flag for pre-fix baseline optional.

### All existing checks must remain green

Preserve table from FIX_1 §7.2:

| Check | Meaning |
|-------|---------|
| DGM 1/(1+children) | Underexplored > overexplored |
| DGM sigmoid(perf) | High reward > low |
| population_stats keys | Telemetry contract |
| propose SearchPlan | Cold start E2E |
| campaign archive_propose | Wiring |
| E5 credit_parent_expansion | children counter |
| U009 bootstrap reward | R08 near zero |
| P1-001 pool exclusion | Bootstrap excluded |
| P1-004 population | Accept count |

### Additional regression

```bash
python verification/verify_async_proposal.py
python verification/verify_mutator_context.py
```

Downstream benefits from sane parent_id — should not regress.

---

## Done-when checklist

- [ ] `_verify_run002_reward_scale_regression` added and passing
- [ ] `_verify_epoch1_parent_not_bootstrap` added and passing
- [ ] `accept_fix1_parent_selection.py` exists with CLI + exit codes
- [ ] `verify_proposal_engine.py` exit 0
- [ ] `run_all_daedalus_verifications.py` exit 0
- [ ] Post-fix dry log or synthetic log passes acceptance parser
- [ ] No production module edits outside verification/

---

## Acceptance criteria (campaign-level)

From FIX_1 §8 — operator runs after all waves:

**Forbidden pattern:**

```text
archive_propose — parent=cold_start::baseline_champion ... boot_excl=True pop>=1
```

**Required after first ACCEPT:**

```text
archive_propose — parent=cand_<id> ... boot_excl=True pop=1 arch=2
```

---

## Appendix: temp archive test helper pattern

```python
def _with_temp_archive(fn):
    # Copy or isolate state/archive for test
    # Use ArchiveManager.add_candidate with controlled rewards
    # Cleanup candidate ids verify_fix1_*
    ...
```

Use patterns from existing `_cleanup_archive` in verify_proposal_engine.py.

---

## FIX_1 campaign closeout

When 1E passes, update `daedalus/RUN_GAPS.JSON`:

- Mark RG-B003, RG-B005, P1-001, P1-004 as closed with verification evidence
- Append phase_journal entry: `phase: fix1_complete`

Notify operator: **FIX_2 agents may start.**

---

## Existing verify fixtures (do not duplicate — extend)

`verify_proposal_engine.py` already contains:

- `_verify_bootstrap_parent_selection()` — P1-001 pool exclusion with `cand_accept_fixture` at reward 0.00037 (~lines 260–316)
- `_verify_population_stats_accept_count()` — P1-004 population==2 with bootstrap + 2 accepts (~lines 319–343)

Your job is to add **run_002 stale reward 2.313 migration** and **epoch-1 reversion** tests plus the **live log parser** — not rewrite existing passing checks.

---

## Cursor spin-up block (copy entire section below)

```text
You are FIX_1-E — an advanced systems engineer who distrusts green unit tests that don't reproduce production failures.

Authority: Agentic_campaign/FIX_1.md and Agentic_campaign/Fix_1_prompts/AGENT_1E_INTEGRATION_VERIFICATION.md.

Mission: Extend verify_proposal_engine.py with run_002 regression tests; create verification/live/accept_fix1_parent_selection.py. Do NOT edit search/ production modules.

Read FIX_1.md §7–§8 and existing _verify_bootstrap_parent_selection in verify_proposal_engine.py before coding.

Exit 0 on:
  cd daedalus && python verification/verify_proposal_engine.py
  cd daedalus && python verification/run_all_daedalus_verifications.py
  cd daedalus && python verification/live/accept_fix1_parent_selection.py --help

Implement all deliverables in AGENT_1E_INTEGRATION_VERIFICATION.md. Append RUN_GAPS closure note when done.
```
