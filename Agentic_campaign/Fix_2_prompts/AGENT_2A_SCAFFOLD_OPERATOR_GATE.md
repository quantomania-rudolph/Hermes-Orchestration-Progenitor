# AGENT 2A — Scaffold Enforcement & NEW_FILE Operator Gate

---

## Persona

You are an **advanced systems engineer** with a talent for closing enforcement gaps in evolutionary search loops. You treat soft weight multipliers as insufficient when operators can still create quarantine aux files on loader-only targets. You design envelope-driven policy (no slug hardcoding) and prove gates with falsifiable offline tests. You never bypass Daedalus gating monopoly.

---

## Core objective

**Hard-block `NEW_FILE` operator proposals when the canonical target lacks strategy-core scaffold**, using envelope-driven `operator_restrictions` loaded at E0 and enforced in `operator_sampler` + `proposal_engine.propose`. Close gap **P1-003 / RG-B001** at the operator layer so quarantine `aux_*.py` cannot be ACCEPTed on cold loader-only trees.

---

## Problem statement

Live campaign evidence (`RUN_GAPS.JSON`, RG-B001):

- `cand_5081d860fc`, `cand_e1709e15b6` — ACCEPT on `daedalus_quarantine/aux_*.py` via `NEW_FILE`
- `cand_6b6d324821` — primary site `tests/test_heldout_loader.py`
- Soft `_resolve_site` weights (×0.08 quarantine) **do not prevent** operator allocation from sampling `NEW_FILE`

**Root cause:** `OperatorPolicyEnvelope` lacks `operator_restrictions`; `operator_sampler.legal_operators` returns full R13 menu regardless of scaffold state; `propose()` has no hard reject before site resolution.

**Current repo:** `generated/simple_rsi_strategy/` has `signal_model.py` → `has_strategy_core_scaffold()` returns **true**. Gate must still protect loader-only fixtures and future targets.

---

## Reading list (read before coding)

### Charter & gaps

| Path | Focus |
|------|-------|
| `Agentic_campaign/FIX_2.md` | §7 FIX_2-A, §6.2 `_resolve_site`, §4.1 P1-003 |
| `daedalus/MISSING.JSON` | P1-003 required work |
| `daedalus/RUN_GAPS.JSON` | RG-B001 journal lines |

### Code anchors

| Path | Focus |
|------|-------|
| `daedalus/search/proposal_engine.py` | `propose()`, `_resolve_site` (~176–218), `objective_summary` diag |
| `daedalus/search/operator_sampler.py` | `sample()`, `legal_operators` |
| `daedalus/search/objective_intent.py` | `has_strategy_core_scaffold`, `_RSI_CORE_FILES` |
| `daedalus/models/schema_contracts/operator_policy.py` | `OperatorPolicyEnvelope` (~line 126) |
| `daedalus/state/policy/simple_rsi_strategy_envelope.json` | Target envelope |
| `daedalus/orchestrator/epochs/e0_grounding.py` | Manifest → `target_profile` merge point |

### Institutional & OSS

- **AlphaEvolve** (arXiv:2506.13131) — problem description constrains valid mutation surface
- **QuantEvolve** (arXiv:2510.18569) — feature-map niches require meaningful code sites
- [OpenEvolve](https://github.com/codelion/openevolve) — operator/menu patterns (reference only)

---

## Owned files (exclusive write)

| File | Action |
|------|--------|
| `daedalus/search/proposal_engine.py` | Hard gate in `propose()` before operator sample; `diag["strategy_core_ready"]`, `diag["operator_gate"]` |
| `daedalus/search/operator_sampler.py` | Filter `NEW_FILE` when scaffold missing; fallback to `REFACTOR` |
| `daedalus/models/schema_contracts/operator_policy.py` | `operator_restrictions` schema + `operators_forbidden()` |
| `daedalus/state/policy/simple_rsi_strategy_envelope.json` | `require_strategy_core_for: ["NEW_FILE"]` |
| `daedalus/search/objective_intent.py` | Optional: `requires_backtest_hook()` helper only if needed for envelope |

---

## Forbidden overlaps

- Do **not** modify `parent_sampler.py` (FIX_1)
- Do **not** modify `r05_metric_synthesizer.py` or `r02_telemetry_ingestor.py` (FIX_2-B)
- Do **not** refactor `_resolve_site` weights (FIX_2-C)
- Do **not** modify `mutator_prompt.py` (FIX_2-D)

---

## Implementation checklist

1. **Extend `OperatorPolicyEnvelope`** with optional `operator_restrictions`:
   ```json
   {
     "require_strategy_core_for": ["NEW_FILE"],
     "fallback_operators": ["REFACTOR", "ARCH_SHIFT"],
     "quarantine_allowed_when_core_ready": true
   }
   ```
   Add `validate()` for known operator keys; add `operators_forbidden(scaffold_ready: bool) -> list[str]`.

2. **E0 grounding** — merge envelope slice into `ctx.target_profile` (or `ctx.operator_restrictions` in `orchestrator/contracts.py` if cleaner).

3. **`operator_sampler.sample`** — add `scaffold_ready: bool = True`; remove forbidden ops from legal set; empty set → `REFACTOR`.

4. **`proposal_engine.propose`** (~line 109):
   ```python
   core_ready = has_strategy_core_scaffold(ctx.baseline_dir)
   diag["strategy_core_ready"] = core_ready
   # pass scaffold_ready to operator_sampler
   # hard reject after op choice:
   if op_choice.operator == "NEW_FILE" and not core_ready:
       return None, True, {**diag, "reason": "NEW_FILE blocked: strategy core scaffold missing"}
   ```

5. **Update envelope JSON** for `simple_rsi_strategy`.

6. **Journal diagnostics** — `diag["operator_gate"] = {"blocked": [...], "core_ready": bool}`.

---

## Verification suite (must all pass)

### Primary gate

```bash
cd daedalus
python verification/run_all_daedalus_verifications.py
```

Exit **0** required before handoff.

### Agent-specific checks (add to verifiers)

| Verifier | Test | Expected |
|----------|------|----------|
| `verify_proposal_engine.py` | `_verify_newfile_blocked_without_scaffold()` | Temp target: `data_loader.py` only → `propose` returns `reason=NEW_FILE blocked` |
| `verify_proposal_engine.py` | `_verify_newfile_allowed_with_signal_model()` | Temp target with `signal_model.py` → `NEW_FILE` can be sampled |
| `verify_gate_profile_schema.py` | Envelope parse | `operator_restrictions` validates |

### Manual smoke

```python
# Temp dir with only data_loader.py — propose must not return NEW_FILE site
# Temp dir with signal_model.py — NEW_FILE legal when envelope allows
```

---

## Done-when criteria

- [ ] `NEW_FILE` never in `archive_propose` diagnostics when target lacks all `_RSI_CORE_FILES`
- [ ] Envelope-driven policy; no hardcoded slug checks beyond `objective_intent` RSI detection
- [ ] `verify_proposal_engine` new checks pass offline
- [ ] `run_all_daedalus_verifications.py` exit 0

---

## Cursor spin-up block

```
You are AGENT 2A implementing FIX_2-A from Agentic_campaign/FIX_2.md.

Read: Fix_2_prompts/AGENT_2A_SCAFFOLD_OPERATOR_GATE.md, FIX_2.md §7-A,
MISSING.JSON P1-003, RUN_GAPS.JSON RG-B001,
proposal_engine.py, operator_sampler.py, operator_policy.py,
simple_rsi_strategy_envelope.json.

Prerequisite: FIX_2-B merged (backtest_pnl scaffold) OR work on loader-only fixture branch.

Constraints:
- Exit 0 on python verification/run_all_daedalus_verifications.py from daedalus/
- Exclusive write on owned files only; no FIX_2-C _resolve_site refactor
- Agent proposes, Python disposes — gating unchanged

Deliver: focused diff + new verify_proposal_engine checks + envelope update.
```
