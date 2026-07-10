# AGENT 2D — objective_summary & Mutator Target-Aware Prompts

---

## Persona

You are an **advanced systems engineer** who treats mutator prompts as **problem descriptions** (AlphaEvolve §2.3). You align LLM mutation context with quant RSI intent: name `backtest_pnl.py`, forbid generic quarantine aux when core is missing, and ensure `objective_summary` propagates fresh through E3. You fix prompt–code drift (`backtest.py` vs `backtest_pnl.py`) with dynamic blocks, not stale string literals.

---

## Core objective

**Enrich `objective_summary` with `backtest_hook=` status** and update mutator/NEW_FILE prompt templates so Cursor mutations target RSI signal and backtest hooks — not loader tests or generic aux helpers. Close **P1-003 / RG-B001** at the prompt layer (complements 2A enforcement and 2C weights).

---

## Problem statement

| Issue | Location | Detail |
|-------|----------|--------|
| Stale file reference | `mutator_prompt._RSI_EVOLVE_BLOCK` | Lists `backtest.py`; canonical uses `backtest_pnl.py` |
| Incomplete summary | `objective_intent.objective_summary` | Reports `strategy_core=` but not `backtest_hook=` |
| Generic NEW_FILE purpose | `newfile_prompt`, `mutator._mutate_new_file` | No RSI contract when core missing |
| Trigger gap | `_rsi_objective_block` | May not fire on `backtest_hook=` substring |

Live outcome: mutator chases loader/quarantine surface despite partial `_RSI_EVOLVE_BLOCK` wiring.

---

## Reading list (read before coding)

### Charter & gaps

| Path | Focus |
|------|-------|
| `Agentic_campaign/FIX_2.md` | §7 FIX_2-D, §6.1 objective_intent, §6.4 mutator_prompt |
| `daedalus/MISSING.JSON` | P1-003 |
| `daedalus/RUN_GAPS.JSON` | RG-B001 mutator-facing evidence |

### Code anchors

| Path | Focus |
|------|-------|
| `daedalus/search/objective_intent.py` | `objective_summary`, `has_strategy_core_scaffold` |
| `daedalus/agents/mutator_prompt.py` | `_RSI_EVOLVE_BLOCK`, `_rsi_objective_block`, `build_mutator_prompt` |
| `daedalus/agents/newfile_prompt.py` | `build_newfile_prompt` |
| `daedalus/agents/mutator.py` | `_mutate_new_file` purpose (~line 375) |
| `daedalus/orchestrator/epochs/e3_e4_verify.py` | `objective_summary(ctx)` at line ~133 |
| `daedalus/search/proposal_engine.py` | `diag["objective_summary"]` → manifest path |

### Institutional & OSS

- **AlphaEvolve** (arXiv:2506.13131) — §2.3 problem description in prompt; task string names evaluator hooks
- **QuantEvolve** (arXiv:2510.18569) — mutations must affect tradable behavior, not test harness
- **Gödel Machine** (Schmidhuber) — self-referential improvement requires explicit utility / objective in context
- [OpenEvolve](https://github.com/codelion/openevolve) — prompt context patterns

---

## Owned files (exclusive write)

| File | Action |
|------|--------|
| `daedalus/search/objective_intent.py` | Add `backtest_hook=present|missing` to RSI summary |
| `daedalus/agents/mutator_prompt.py` | Update `_RSI_EVOLVE_BLOCK`; extend `_rsi_objective_block` triggers |
| `daedalus/agents/newfile_prompt.py` | Restriction block when `strategy_core=missing` |
| `daedalus/agents/mutator.py` | NEW_FILE purpose references signal/backtest contracts |
| `daedalus/orchestrator/epochs/e3_e4_verify.py` | Ensure fresh summary on plan manifest |

---

## Forbidden overlaps

- Do **not** modify `proposal_engine` weights (FIX_2-C)
- Do **not** modify `mutation_context.py` (FIX_3)
- Do **not** modify R02/R05 (FIX_2-B)

---

## Implementation checklist

1. **`objective_intent.objective_summary`** — RSI branch:
   ```python
   hook = "present" if (root / "backtest_pnl.py").is_file() else "missing"
   return f"{base}; intent=evolve RSI...; strategy_core={core}; backtest_hook={hook}; deprioritize test-only aux mutations"
   ```

2. **`mutator_prompt._RSI_EVOLVE_BLOCK`** — primary files:
   ```
   - backtest_pnl.py — run_backtest, performance_objective (primary trading eval hook)
   - signal_model.py (# EVOLVE-BLOCK: rsi_signal)
   - data_loader.py — bar loading feeding signal pipeline
   ```
   Remove stale `backtest.py` unless file exists (dynamic optional).

3. **`_rsi_objective_block`** — trigger on `backtest_hook=`, `backtest_pnl`, `simple_rsi_strategy`, `signal_model`.

4. **`newfile_prompt.build_newfile_prompt`** — when `strategy_core=missing`:
   ```
   ## Restriction
   Do NOT create generic math/util helpers. Module must integrate with signal_model or backtest_pnl interface.
   ```

5. **`mutator._mutate_new_file`** — purpose template references `signal_model.generate_signals` or `backtest_pnl.run_backtest` for RSI targets.

6. **E3 path** — confirm `e3_e4_verify.py` passes enriched summary to mutator manifest.

---

## Verification suite (must all pass)

### Primary gate

```bash
cd daedalus
python verification/run_all_daedalus_verifications.py
```

### Extend `verify_mutator_context.py` (P2-006)

| Assert | Expected |
|--------|----------|
| RSI prompt content | `backtest_pnl.py` present in generated prompt |
| Hook trigger | `backtest_hook=present` activates `_RSI_EVOLVE_BLOCK` |
| NEW_FILE restriction | Generic aux forbidden when `strategy_core=missing` |

### New verifier — `verify_objective_intent.py`

| Fixture | Expected summary substrings |
|---------|----------------------------|
| Loader-only temp dir | `strategy_core=missing`, `backtest_hook=missing` |
| Signal-only | `strategy_core=present`, `backtest_hook=missing` |
| Full scaffold (post-2B) | `backtest_hook=present` |

Use temp dirs; match existing `check()` pattern (no pytest dependency for verifier module).

---

## Done-when criteria

- [ ] Mutator prompt names `backtest_pnl.py` for `simple_rsi_strategy`
- [ ] NEW_FILE prompt forbids generic aux when core missing
- [ ] `objective_summary` includes `backtest_hook` field
- [ ] `verify_mutator_context` P2-006 extended checks pass
- [ ] `run_all_daedalus_verifications.py` exit 0

---

## Cursor spin-up block

```
You are AGENT 2D implementing FIX_2-D from Agentic_campaign/FIX_2.md.

Read: Fix_2_prompts/AGENT_2D_OBJECTIVE_MUTATOR_PROMPTS.md, FIX_2.md §7-D,
objective_intent.py, mutator_prompt.py, newfile_prompt.py, mutator.py, e3_e4_verify.py.

Prerequisite: FIX_2-B merged (backtest_pnl.py exists for hook=present tests).

Constraints:
- Prompt-layer only — no proposal_engine weight changes
- FIX_3 must not strip backtest_hook from manifest later
- Exit 0 on python verification/run_all_daedalus_verifications.py

Deliver: enriched objective_summary + RSI blocks + verify_objective_intent.py + P2-006 extensions.
```
