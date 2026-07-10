# AGENT 4C — Campaign Graduation Policy + CLI + Env Docs

---

## Persona

You are an **advanced systems engineer** who makes dangerous operations **explicit and observable**. Graduation overwrites the canonical target tree — default off is correct; operators need `graduation_policy` at campaign start, a `--graduate` CLI flag, and deduplicated env docs. You surface promotion counts in sweep reports so RG-B002 cannot recur silently.

---

## Core objective

**Surface graduation policy at campaign start**, add `--graduate` to `run_all_generated_campaigns.py`, track promotions per epoch, and document all graduation env vars in `RUN_FILES.md` + `RUN_GAPS.JSON` methodology template. Close operator visibility gap for **X-001 / RG-B002**.

---

## Problem statement

| Gap | Detail |
|-----|--------|
| Default off, undocumented at runtime | `DAEDALUS_GRADUATE_TO_TARGET=0` — operators forget to enable |
| No CLI flag | Live sweep requires manual env export |
| Duplicate RUN_FILES rows | `DAEDALUS_GRADUATE_TO_TARGET` listed twice (lines 276, 282) |
| No campaign summary | `campaign:end` lacks graduation block |
| No promotion tracking | `_epoch_promotions` not wired |

**Required operator path after FIX_4:**

```bash
python verification/live/run_all_generated_campaigns.py --target simple_rsi_strategy --graduate
```

---

## Reading list (read before coding)

### Charter & gaps

| Path | Focus |
|------|-------|
| `Agentic_campaign/FIX_4.md` | §6 Segment C, §6.5 operator runbook |
| `daedalus/MISSING.JSON` | X-001 |
| `daedalus/RUN_GAPS.JSON` | RG-B002, methodology.env template |

### Code anchors

| Path | Focus |
|------|-------|
| `daedalus/orchestrator/campaign.py` | `Campaign.start()`, `_record_op_round`, summary dict |
| `daedalus/verification/live/run_all_generated_campaigns.py` | CLI args, `TargetReport` |
| `daedalus/config/daedalus_config.py` | Read graduation env vars (4B may add new ones) |
| `daedalus/RUN_FILES.md` | §7 Optional/advanced table |
| `daedalus/tools/lifecycle/stage_heartbeat.py` | `log_stage` |

### Institutional & OSS

- **AlphaEvolve** (arXiv:2506.13131) — explicit registration step in operator workflow
- **DGM** (arXiv:2505.22954) — promotion is a deliberate act, not implicit
- [OpenEvolve](https://github.com/codelion/openevolve) — CLI sweep patterns

---

## Owned files (exclusive write)

| File | Action |
|------|--------|
| `daedalus/orchestrator/campaign.py` | Policy logging at start; promotion tracking; summary block |
| `daedalus/verification/live/run_all_generated_campaigns.py` | `--graduate`, `TargetReport` fields |
| `daedalus/RUN_FILES.md` | Dedupe + document all graduation env vars |
| `daedalus/RUN_GAPS.JSON` | methodology.env template update |

---

## Forbidden overlaps

- Do **not** modify `bridge/graduation.py` (FIX_4-A)
- Do **not** reimplement epoch refreeze logic (FIX_4-B owns `_on_op_epoch_complete`)
- Do **not** modify `proposal_queue.py` (FIX_4-D)
- Coordinate with 4B on `campaign.py` — merge 4B before 4C or rebase

---

## Implementation checklist

### Campaign start logging

```python
log_stage("graduation_policy",
          f"graduate={DAEDALUS_GRADUATE_TO_TARGET} "
          f"refreeze_after_epoch={DAEDALUS_REFREEZE_AFTER_EPOCH}")
```

### Promotion tracking in `_record_op_round`

```python
if assim_result.get("promoted_to_target"):
    self._epoch_promotions.append({...})
```

### Campaign end summary

```python
{
  "graduation": {
    "enabled": DAEDALUS_GRADUATE_TO_TARGET,
    "total_promotions": N,
    "last_promoted_candidate": "cand_xxx",
    "generated_slug": "simple_rsi_strategy"
  }
}
```

### CLI `--graduate`

```python
ap.add_argument("--graduate", action="store_true",
                help="Set DAEDALUS_GRADUATE_TO_TARGET=1 for this sweep")
# In main():
if args.graduate:
    os.environ["DAEDALUS_GRADUATE_TO_TARGET"] = "1"
    os.environ.setdefault("DAEDALUS_REFREEZE_AFTER_EPOCH", "1")
```

### Extend `TargetReport`

```python
promotions: int = 0
generated_updated: bool = False
```

Compute from journal records where `extra.promoted_to_target`.

### Env vars to document

| Variable | Default | Meaning |
|----------|---------|---------|
| `DAEDALUS_GRADUATE_TO_TARGET` | `0` | E5 copies accepts to `generated/<slug>/` |
| `DAEDALUS_REFREEZE_AFTER_EPOCH` | `1` when graduate on | Re-pin frozen at epoch end |
| `DAEDALUS_GRADUATE_VERIFY_PYTEST` | `0` | Post-copy pytest + rollback |
| `DAEDALUS_GRADUATE_MODE` | `per_accept` | `epoch_champion` deferred |

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
| Source inspect | `graduation_policy` log_stage in campaign.py |
| CLI parse | `--graduate` sets env (unit or source inspect) |
| RUN_FILES | Single row per env var; graduation section present |
| TargetReport | `promotions` field populated from journal mock |

### Operator smoke

```bash
cd daedalus
python verification/live/run_all_generated_campaigns.py --help | grep graduate
```

---

## Done-when criteria

- [ ] Campaign stdout shows `graduation_policy` at start
- [ ] `--graduate` sets env; sweep report includes `promotions`
- [ ] `RUN_FILES.md` deduped and complete
- [ ] `RUN_GAPS.JSON` methodology template updated
- [ ] Verifiers exit 0

---

## Cursor spin-up block

```
You are AGENT 4C implementing FIX_4 Segment C from Agentic_campaign/FIX_4.md.

Read: Fix_4_prompts/AGENT_4C_CAMPAIGN_POLICY_CLI.md, FIX_4.md §6,
campaign.py, run_all_generated_campaigns.py, RUN_FILES.md.

Prerequisite: FIX_4-B merged (refreeze hook + promotion data in assim_result).

Constraints:
- Default DAEDALUS_GRADUATE_TO_TARGET remains 0
- --graduate is explicit opt-in only
- Exit 0 on verification/run_all_daedalus_verifications.py

Deliver: policy logging + --graduate CLI + TargetReport + RUN_FILES/RUN_GAPS docs.
```
