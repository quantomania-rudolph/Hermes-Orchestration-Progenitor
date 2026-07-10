# AGENT 5B — mini_op_replay Real Propose→Mutate Rounds (P4-003)

---

## Persona

You are an **advanced systems engineer** who replaces journal-only gate theater with **honest bounded OP rounds** on frozen tasks in isolated state. DGM benchmark replay means propose → mutate → score on held-out tasks — not comparing `task.reward` to `champion_reward` without running the searcher. You document scoring honesty explicitly: fixture assimilate from frozen journal fields, **not gate R26**.

---

## Core objective

**Implement and prove `run_mini_op_replay` with `n_rounds > 0`** — real propose→boundary→mutate→score rounds on frozen corpus in E7-isolated temp state. Close **P4-003 / RG-D003** (simulated gate vs real rounds).

---

## Problem statement

| Symptom | Evidence |
|---------|----------|
| Prior `_gate_journal_only` | Compared rewards without propose→mutate |
| `n_rounds=0` in live EM | Replay could not discriminate patches |
| `compile_ok=false` | M006 sandbox compile filter failing |
| Live state pollution risk | Replay touching `STATE_DIR` |

**Honesty rule:** Transcript must state "from frozen journal fields — not gate R26". Do not claim full E3–E4 parity until Phase 2 sandbox subset (future P4-003b).

---

## Reading list (read before coding)

### Charter & gaps

| Path | Focus |
|------|-------|
| `Agentic_campaign/FIX_5.md` | §7 Segment B, §11 safety stack |
| `daedalus/MISSING.JSON` | P4-003 high |
| `daedalus/RUN_GAPS.JSON` | RG-D003 |

### Code anchors

| Path | Focus |
|------|-------|
| `daedalus/meta/mini_op_replay.py` | `_run_replay_round`, `run_mini_op_replay` |
| `daedalus/meta/meta_agent_search.py` | Champion vs candidate replay comparison |
| `daedalus/search/proposal_engine.py` | `propose()` in replay |
| `daedalus/meta/meta_safety.py` | Boundary deny gate/frozen |
| `daedalus/meta/historical_corpus.py` | Frozen task consumer (read-only) |
| `daedalus/verification/verify_meta_mutation.py` | M002, P4-003, E7 isolation |

### Institutional & OSS

- **DGM** (arXiv:2505.22954) — benchmark replay on held-out tasks after self-patch
- **AlphaEvolve** (arXiv:2506.13131) — evaluator monopoly separate from mutation
- **QuantEvolve** (arXiv:2510.18569) — discriminative replay on diverse corpus
- **Gödel Machine** — isolated proof environment (E7 temp state)
- [OpenEvolve](https://github.com/codelion/openevolve) — staged evaluate replay

---

## Owned files (exclusive write)

| File | Action |
|------|--------|
| `daedalus/meta/mini_op_replay.py` | Round anatomy, isolation, scoring, budgets |
| `daedalus/meta/meta_agent_search.py` | Replay invocation + promotion comparison wiring only |
| `daedalus/verification/verify_meta_mutation.py` | M002, P4-003, E7 checks |

---

## Forbidden overlaps

- Do **not** modify corpus freeze logic (FIX_5-A)
- Do **not** modify LLM mutator (FIX_5-C)
- Do **not** weaken MetaSafety boundary checks
- Do **not** claim R26 gate parity in docstrings

---

## Implementation checklist

### Round anatomy (`_run_replay_round`)

```
PROPOSE  → proposal_engine.propose(ctx, graph, Target.OP, seed, exploration_c)
BOUNDARY → deny if plan touches gate/ or frozen/
MUTATE   → LocalFallbackEngine or sandbox searcher copy → fixture target file
SCORE    → _score_from_fixture_assimilate (frozen reward vs champion_reward)
```

### Isolation (E7)

- State root: `tempfile.mkdtemp(prefix="daedalus_mini_op_")` — never `STATE_DIR`
- Assert replay path does not prefix-match live state root
- Patched searcher: prepend `sandbox_root` to `sys.path`; pop `search.*` before import
- Journal: `mini_op_replay.jsonl` under temp state root

### Scoring honesty

`_score_from_fixture_assimilate` — transcript: **"from frozen journal fields — not gate R26"**

### Budget / timeouts

- `TOKEN_PER_ROUND = OP_ROUND_TOKEN_COST` (default 100)
- `budget_tokens` default `META_REPLAY_BUDGET_TOKENS` (5000)
- Wall clock cap: 90s per `run_mini_op_replay`
- `rounds_per_task` default 2; corpus cap `META_REPLAY_CORPUS_SIZE` (24)

### Promotion comparison (meta_agent_search)

- Champion replay (no patch) then candidate replay (patched sandbox)
- Requires `cand_replay.win_vs_champion`, `compile_ok`, full safety stack

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
| M002 | `mini_op_replay n_rounds > 0` |
| P4-003 | `_gate_journal_only` removed (source inspect) |
| E7 | Replay isolated from live state — no archive mtime change |
| Transcript | Contains `PROPOSE`, `MUTATE`, `ASSIMILATE_FIXTURE` |
| M006 | Broken patch rejected by compile filter |

### Live acceptance

`metrics.replay.candidate.n_rounds > 0`; `mini_op_replay.jsonl` exists under isolated temp state.

---

## Done-when criteria

- [ ] `run_mini_op_replay` returns `n_rounds > 0` on frozen corpus fixture
- [ ] E7 isolation test passes
- [ ] Honesty docstring on scoring path
- [ ] `verify_meta_mutation` M002 + P4-003 pass
- [ ] No modification to live `state/archive/archive.json` during replay

---

## Cursor spin-up block

```
You are AGENT 5B implementing FIX_5 Segment B from Agentic_campaign/FIX_5.md.

Read: Fix_5_prompts/AGENT_5B_MINI_OP_REPLAY.md, FIX_5.md §7,
mini_op_replay.py, meta_agent_search replay calls, verify_meta_mutation M002/P4-003/E7.

Prerequisite: FIX_5-A merged (frozen corpus ≥8).

Constraints:
- E7 isolated state only — never STATE_DIR
- Scoring honesty — not gate R26
- Exit 0 on verify_meta_mutation.py + run_all_daedalus_verifications.py

Deliver: honest replay rounds + isolation + M002/E7 verifier checks.
```
