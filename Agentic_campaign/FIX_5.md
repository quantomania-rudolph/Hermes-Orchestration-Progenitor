# FIX_5 — Meta-RSI Searcher Self-Improvement

**Charter ID:** `FIX_5`  
**Phase:** P4 — RSI-on-RSI (meta agent search)  
**Gap IDs:** P4-001 … P4-009, RG-D001 … RG-D005, P4-T001 … P4-T003  
**Owner agent:** D_meta_rsi (`RUN_GAPS.JSON` → `agent_assignments.D_meta_rsi`)  
**Status:** Charter — implementation pending live proof  
**Generated:** 2026-06-17  
**Primary scope:** `daedalus/meta/*`, `daedalus/orchestrator/epochs/em_meta.py`, `daedalus/verification/verify_meta_mutation.py`

---

## 0. Executive summary

P4 is the **RSI-on-RSI** layer: the system improves its own **searcher** (`search/*.py`), not the target strategy tree. Institutional references:

| Reference | What we borrow | Daedalus mapping |
|-----------|----------------|------------------|
| **DGM** (arXiv:2505.22954 §C.3) | Parent reads eval logs → foundation model proposes feature → implements patch on own Python codebase → benchmark replay → archive | `log_analyzer` → `meta_mutator_llm` → `stage_patch_in_sandbox` → `mini_op_replay` → `MetaArchive` |
| **ADAS** (arXiv:2408.08435) | Meta-agent programs agents in executable code; archive-conditioned search | `meta_agent_search.run_meta_agent_search` over whitelisted `search/` |
| **AlphaEvolve** (arXiv:2506.13131) | Co-evolved meta-prompt DB; evaluator monopoly; program DB inspirations | `MetaPromptDB`, frozen corpus hash-lock, gate stack R30/R33/R51 |

**Live verdict (RUN_GAPS `run_gaps_simple_rsi_002`):** `meta_ran=false`. Campaign aborted mid epoch 1; EM never scheduled. Meta path is **wired in code** and **green in `verify_meta_mutation.py`**, but not proven on a completed campaign with journal corpus, LLM patches, and `searcher_code_promoted` in stdout.

**This charter closes:** frozen corpus ≥8 tasks, honest mini-OP replay, LLM-default meta mutator, EM epoch execution with `meta_ran=true` proof, phased whitelist + champion policy fields wired to OP.

---

## 1. Problem statement

The operational loop (E0→E5) mutates **target** code under gate monopoly. P4 mutates **how we search and mutate** — the proposal engine, prompt sampler, experience replay, and (eventually) parent selection. Without P4:

- DGM-style parent selection bugs (P1-001 / RG-B003) cannot self-heal via meta.
- Mutation context stays empty (P2-001 / RG-C003) because prompt/inspiration knobs are static.
- `DAEDALUS_META_MODE=agent_search` is configured in live runs but **never executes**.

P4 must **not** weaken the measurement monopoly. Meta mutators propose; **mini-OP replay + safety stack** dispose. Same principle as gating Wave 1–3 (AGENT_D): agent suggests, Python promotes.

---

## 2. Architecture — two-loop spine

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Campaign.start()                                 │
│  E5: freeze_eval_corpus_snapshot()  ← hash-lock BEFORE any OP accept   │
└─────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐     cadence: epoch_index > 0 && index % META_EPOCH_CADENCE == 0
│  OP epochs      │     default META_EPOCH_CADENCE = 2 (EM at index 2, 4, …)
│  E0→E5          │
└────────┬────────┘
         │ journal ACCEPT records
         ▼
┌─────────────────┐
│  EM epoch       │  run_em() → _run_em_agent_search()
│  (META)         │       → run_meta_agent_search()
└────────┬────────┘
         │
         ├── MetaArchive.sample_parent (DGM archive)
         ├── analyze_meta_logs (DGM §C.3 log conditioning)
         ├── propose_searcher_patch (LLM default / deterministic offline fallback)
         ├── MetaSafety: boundary, R33, M006 compile, capability, budget
         ├── run_mini_op_replay (frozen corpus, isolated state E7)
         ├── R51 counterfactual, R31 meta-benchmark
         └── promote → shadow champion + optional repo patch (DAEDALUS_META_APPLY_PATCH)
```

**Key files:**

| Module | Role |
|--------|------|
| `meta/meta_agent_search.py` | Orchestrates one meta-RSI iteration; promotion gate cascade |
| `meta/meta_mutator.py` | Whitelist read, diff staging, offline fallback |
| `meta/meta_mutator_llm.py` | Cursor/LLM unified diff path (P4-007) |
| `meta/mini_op_replay.py` | Bounded propose→mutate replay on frozen corpus |
| `meta/historical_corpus.py` | E5 journal freeze, diversity picker, hash-lock |
| `meta/champion_apply.py` | Hot-load promoted searcher; OP epoch policy injection |
| `orchestrator/epochs/em_meta.py` | EM entry; `agent_search` vs legacy `primitive` |
| `verification/verify_meta_mutation.py` | Contract tests M001/M002/M006/M007, P4-003/004/007 |

---

## 3. Gap inventory — P4-001 through P4-009

### P4-001 — META epoch never ran in live campaigns (CRITICAL)

**Evidence:** `RUN_GAPS.JSON` `run_status.meta_ran=false`; `run_001` and `run_002` completed OP epochs 0–1 only; `run_002` aborted before epoch 2.

**Root cause:** Operator abort + insufficient `max_epochs` progress. `EpochController.plan_epoch`: `is_meta = epoch_index > 0 and (epoch_index % META_EPOCH_CADENCE == 0)`. With cadence 2, first META is **epoch index 2**. Aborted campaigns never reach it.

**Required work:**

1. Complete a campaign through epoch index ≥2 without operator abort.
2. Journal must contain EM phase entries: `searcher_promoted`, `compile_ok`, `code_patch_applied` / `repo_patch_applied`.
3. Campaign summary must expose `meta_ran: true` (new field — see Segment D).
4. `phase_journal` entry at `epoch_complete` for META with `target=META`.

**Acceptance:** Live log line `searcher_code_promoted` OR honest `candidate_discarded` with `n_rounds > 0` and `frozen_corpus_size >= 8`.

---

### P4-002 — Meta mutator deterministic constant-insert, not LLM (CRITICAL)

**Evidence:** Historical runs used `source=deterministic_log_conditioned`; patches only `_META_EXPLORATION_DEFAULT` and `META_PROMPT_INSPIRATION_K`.

**Current state:** `meta_mutator.py` now defaults to `meta_mutator_llm.propose_searcher_patch_llm` when `DAEDALUS_META_OFFLINE != 1` and Cursor available. Offline path labeled `deterministic_log_conditioned_fallback`.

**Required work:**

1. Live campaign must log `patch_source=llm_log_conditioned` at least once.
2. `verify_meta_mutation.py` keeps offline deterministic for CI; live stack uses WSL Cursor (`HERMES_CURSOR_EXECUTION=wsl_native`).
3. Budget gate: `META_REPLAY_BUDGET_TOKENS * 0.15` per LLM call.

**Acceptance:** Journal `extra.patch_source == "llm_log_conditioned"` on promoted or attempted meta candidate.

---

### P4-003 — mini-OP replay simulated gate vs real rounds (HIGH)

**Evidence:** Prior `_gate_journal_only` compared task.reward to champion_reward without propose→mutate.

**Current state:** `mini_op_replay.py` implements `_run_replay_round`: propose → boundary check → `_mutate_fixture` → `_score_from_fixture_assimilate`. Scoring uses **frozen journal assimilate fields**, explicitly **not** R19–R34 gate cascade. `verify_meta_mutation.py` asserts `_gate_journal_only` removed.

**Honesty rule:** Module docstring and assimilate transcript must state "not gate R26". Do not claim full E3–E4 parity until sandbox subset runs real `run_e3_e4` on fixture branches (future P4-003b).

**Required work:**

1. `run_mini_op_replay` returns `n_rounds > 0` on live EM.
2. Isolated journal at `mini_op_replay.jsonl` under temp state root (E7).
3. Optional Phase 2: K rounds with real gate on sandbox copy of frozen task branches.

**Acceptance:** `metrics.replay.candidate.n_rounds > 0`; per-task `transcript` contains `PROPOSE`, `MUTATE`, `ASSIMILATE_FIXTURE`.

---

### P4-004 — Frozen META corpus too small / bootstrap-sourced (HIGH)

**Evidence:** `meta_code_mutation_report: frozen_corpus_tasks=2`; bootstrap not campaign journal.

**Current state:** `historical_corpus.freeze_from_journal(min_tasks=8)` with `_diversify_tasks` (operator/site round-robin). `campaign.start()` calls `freeze_eval_corpus_snapshot()` at boot. Padding with bootstrap only when journal < 8 accepts.

**Required work:**

1. FIX_1–4 must produce ≥8 diverse OP ACCEPT journal records before EM (cross-dep).
2. Corpus diversity: ≥3 operators among {REFACTOR, NEW_FILE, ARCH_SHIFT}; ≥3 distinct `site.file` values.
3. `content_hash` in `META_FROZEN_CORPUS_PATH`; `MetaSafety.frozen_corpus_intact()` true at EM entry.
4. No rebuild from live journal during meta scoring — snapshot frozen at campaign start.

**Acceptance:** `frozen_corpus_size >= 8` in meta agent search result; `verify_meta_mutation` P4-004 check passes.

---

### P4-005 — Promotion journal-only by default (MEDIUM)

**Evidence:** `DAEDALUS_META_APPLY_PATCH=0` default; repo `search/` unchanged unless flag set.

**Current state:** `champion_apply.apply_searcher_code_patch` journals every attempt with `repo_patch_applied: bool`. `meta_agent_search` message: `searcher_code_promoted (journal-only — set DAEDALUS_META_APPLY_PATCH=1 to write repo)`.

**Required work:**

1. Operator checklist documents human-gated apply path.
2. `searcher_patch_journal.jsonl` entries for all promotion attempts.
3. Shadow champion (`save_champion`) updates even when repo patch disabled — OP reads policy via `apply_champion_for_op_epoch`.

**Acceptance:** Promoted meta candidate has journal entry; `repo_patch_applied` reflects operator intent.

---

### P4-006 — META whitelist excludes core search engine (MEDIUM)

**Evidence:** `_DAY1_PATHS` historically operator_sampler + prompt_sampler only; `parent_sampler`, `program_database` behind `META_ALLOW_ENGINE_SELF_EDIT=0`.

**Current state:** Day-1 defaults include `experience_replay.py`. Full whitelist in `daedalus_config.META_WHITELIST_PATHS`. Engine paths in `META_ENGINE_PATHS` gated separately.

**Phased expansion (E14):**

| Phase | Paths | Prerequisite |
|-------|-------|--------------|
| Day-1 | `operator_sampler`, `prompt_sampler`, `experience_replay` | P4-001 live EM proof |
| Day-2 | `learned/ucb_bandit.py`, `agents/mutator_prompt.py` | mini-OP regression per module |
| Day-3 | `parent_sampler`, `program_database` | `META_ALLOW_ENGINE_SELF_EDIT=1` + human signoff R40 |

**Acceptance:** Each phase adds verify test + mini-OP replay suite before whitelist merge.

---

### P4-007 — LLM meta mutator (HIGH)

**Implementation:** `meta/meta_mutator_llm.py` — `build_meta_mutator_prompt`, `extract_unified_diff`, Cursor CLI via `run_agent_cli`, `mock_transcript` for tests.

**Flow:**

1. `read_whitelisted_source(rel)` — real file content.
2. `MetaPromptDB().champion_directive()` — AlphaEvolve-style meta-prompt conditioning.
3. LLM returns unified diff; must apply cleanly via `apply_unified_diff`.
4. `source="llm_log_conditioned"` on success.

**Fallback:** Return `None` → `meta_mutator._propose_searcher_patch_offline` with warning log.

**Acceptance:** `verify_meta_mutation` P4-007 mock path; live path produces non-trivial diff on `prompt_sampler.py` or `operator_sampler.py`.

---

### P4-008 — Open-ended engine self-edit (MEDIUM)

**Reference:** DGM future work — parent/archive process mutable.

**Gate:** `DAEDALUS_META_ALLOW_ENGINE_SELF_EDIT=1` (config `META_ALLOW_ENGINE_SELF_EDIT`). Off by default.

**Required work:** Prove mini-OP catches `parent_sampler` regressions before enabling. Human escalation via R40 signoff.

**Deferred:** Until Day-3 whitelist phase complete and P1-001 cold-start fix verified.

---

### P4-009 — Co-evolved meta prompt invention via LLM (MEDIUM)

**Reference:** AlphaEvolve separate meta-prompt DB co-evolution.

**Current state:** `MetaPromptDB` — 4 hand-seeded variants; `register_variant()` not called from meta loop.

**Required work:**

1. LLM proposes new meta-prompt variant from OP accept/fail logs.
2. Score by downstream OP accept rate in shadow epoch.
3. `prompt_db.evaluate_champion()` credits winning variant.

**Cross-link:** P3-003; FIX_5 Segment E wires `explore_probability` etc. from champion manifest.

---

## 4. Live gap journal — RG-D001 through RG-D005

### RG-D001 — META epoch not reached (CRITICAL)

Maps to **P4-001**. Live evidence: `run_002` epoch 1 in progress at abort; `meta_ran=false`.

**Fix_5 action:** Run campaign `max_epochs >= 3` on `simple_rsi_strategy` after FIX_1–4 journal corpus exists. Inspect EM diagnostics in campaign return payload `epochs[]` where `is_meta=true`.

---

### RG-D002 — Deterministic meta mutator only (CRITICAL)

Maps to **P4-002**, **P4-007**. Evidence: `meta_mutator.py source=deterministic_log_conditioned` in pre-fix runs.

**Fix_5 action:** Ensure `DAEDALUS_META_OFFLINE=0` in live env; Cursor API key present; log `patch_source` in stdout and journal.

---

### RG-D003 — Frozen corpus tiny; mini-OP cannot discriminate (HIGH)

Maps to **P4-004**, **P4-003**. Evidence: `frozen_corpus_tasks=2`, `n_rounds=0`, `compile_ok=false`.

**Fix_5 action:** Segment A freeze; Segment B replay rounds; root-cause `compile_ok` via M006 sandbox compile filter.

---

### RG-D004 — Whitelist blast radius too narrow (MEDIUM)

Maps to **P4-006**. Evidence: core RSI gaps in `parent_sampler` / `experience_replay` unreachable.

**Fix_5 action:** Segment E phased expansion; experience_replay already in day-1 defaults — verify live patches can target it.

---

### RG-D005 — shadow_champion dual spine (MEDIUM)

Maps to **P4-T002**. Evidence: `meta_agent_search._live_champion_manifest` loads `shadow_champion` on fallback.

**Fix_5 action:** Deprecate `primitive` mode except `DAEDALUS_LEGACY_META=1`. Single champion source: `MetaArchive` + `champion_policy.json` from agent_search promotion.

---

## 5. Theater gaps — P4-T001 through P4-T003

### P4-T001 — search_policy fields not read by OP spine

**Evidence:** `champion_policy.json` stores `explore_probability`, `thompson_scale`, `entropy_bonus`; only `exploration_c` + `parent_temperature` affect `proposal_engine`.

**Fix_5 Segment E:** Wire remaining fields or remove from manifest to avoid false confidence.

### P4-T002 — Legacy primitive/shadow_champion META modes

**Evidence:** `em_meta.py` primitive branch; U006 toy convergence; R33 `lambda True` in primitive path.

**Mitigation:** Default `agent_search`; `DAEDALUS_LEGACY_META=0` blocks primitive unless explicit.

### P4-T003 — R51 synthetic workloads in meta

**Evidence:** `_replay_to_r51` uses linearly-decaying fake workloads.

**Mitigation:** Document as advisory; prefer `cand_replay.r51_delta` from real replay means when `n_rounds > 0`.

---

## 6. Segment A — Historical corpus freeze ≥8 tasks from E5 journal (P4-004)

### 6.1 Objective

Provide a **hash-locked, diverse, held-out** evaluation set for meta promotion. Meta must not grade itself on tasks the current searcher could have biased after campaign start.

### 6.2 Data contract — `HistoricalTask`

```python
@dataclass
class HistoricalTask:
    task_id: str           # candidate_id from journal ACCEPT
    target_slug: str
    operator: str          # REFACTOR | NEW_FILE | ARCH_SHIFT | ...
    site: dict             # { "file": "...", "telemetry": {...} }
    reward: float
    measured_delta: dict[str, float]
    champion_reward: float # baseline to beat on replay
    engine: str
```

### 6.3 Freeze pipeline

1. **Campaign boot** (`campaign.py:78-79`): `freeze_eval_corpus_snapshot()` — first caller wins; subsequent calls return existing snapshot.
2. **Journal harvest** (`rebuild_from_journal`): ACCEPT + `target==OP` + `reward >= min_reward`.
3. **Diversification** (`_diversify_tasks`): round-robin across operators until `min_tasks` met.
4. **Padding** (only if needed): `bootstrap_corpus_tasks()` then synthetic `freeze_pad_*` — **live proof should not rely on pads**.
5. **Hash-lock**: `content_hash = sha256_json(payload)` written to `META_FROZEN_CORPUS_PATH`.

### 6.4 Cross-dependency: FIX_1–4

| FIX | Contribution to corpus |
|-----|------------------------|
| FIX_1 (P1 archive) | Real ACCEPT parents with comparable R08 rewards |
| FIX_2 (P2 mutation) | Non-empty site/operator diversity in journal |
| FIX_3 (P3 co-evolution) | Lessons/replay metadata in journal extra |
| FIX_4 (gating E2E) | Valid `measured_delta` and gate-verified rewards |

Without FIX_1–4 journal quality, freeze pads with bootstrap — **meta replay becomes theater** (RG-D003).

### 6.5 Operator checklist — Segment A

- [ ] Before campaign: confirm `generated/<slug>/` has signal/backtest scaffold (not loader-only).
- [ ] After epoch 0: ≥3 ACCEPT with distinct operators logged.
- [ ] At campaign start: log `frozen_corpus_snapshot n_tasks=… content_hash=…`.
- [ ] Before EM: `MetaSafety.frozen_corpus_intact()` → true.
- [ ] Corpus file path: `daedalus/frozen/meta_corpus/frozen_corpus.json`.

### 6.6 Verification

```bash
cd daedalus && python verification/verify_meta_mutation.py
# Expect: [OK] P4-004: frozen corpus has >=8 tasks
# Expect: [OK] frozen corpus snapshot hash-locked (E5)
```

---

## 7. Segment B — mini_op_replay real propose→mutate rounds (P4-003)

### 7.1 Objective

Replace journal-only gate simulation with **honest bounded OP rounds** on frozen tasks in **isolated state** (E7/A13).

### 7.2 Round anatomy (`_run_replay_round`)

```
PROPOSE  → proposal_engine.propose(ctx, graph, Target.OP, seed, exploration_c)
BOUNDARY → deny if plan touches gate/ or frozen/
MUTATE   → LocalFallbackEngine or sandbox searcher copy → fixture target file
SCORE    → _score_from_fixture_assimilate (frozen reward vs champion_reward)
```

### 7.3 Isolation guarantees

- State root: `tempfile.mkdtemp(prefix="daedalus_mini_op_")` — never `STATE_DIR`.
- Assert: replay path does not prefix-match live state root.
- Optional patched searcher: prepend `sandbox_root` to `sys.path`; pop `search.*` modules before import.

### 7.4 Scoring honesty

`_score_from_fixture_assimilate` compares operator-matched reward against `task.champion_reward`. Transcript explicitly states: **"from frozen journal fields — not gate R26"**.

This is intentional: full E3–E4 on K frozen branches is Phase 2 (higher cost). Current design matches DGM **benchmark replay on held-out tasks**, not full production gate.

### 7.5 Budget and timeouts

- `TOKEN_PER_ROUND = OP_ROUND_TOKEN_COST` (default 100).
- `budget_tokens` default `META_REPLAY_BUDGET_TOKENS` (5000).
- Wall clock cap: 90s per `run_mini_op_replay` invocation.
- `rounds_per_task` default 2; corpus cap `META_REPLAY_CORPUS_SIZE` (24).

### 7.6 Promotion comparison

`meta_agent_search` runs champion replay (no patch) then candidate replay (patched sandbox). Promotion requires:

- `cand_replay.win_vs_champion` — mean_reward and accept_rate ≥ champion.
- `compile_ok` from M006 `compile_capability_filter`.
- Full safety stack (boundary, R33, capability, R51, R31).

### 7.7 Operator checklist — Segment B

- [ ] EM journal shows `replay.champion.n_rounds > 0`.
- [ ] EM journal shows `replay.candidate.n_rounds > 0` when compile_ok.
- [ ] `mini_op_replay.jsonl` exists under isolated temp state.
- [ ] No modification to live `state/archive/archive.json` mtime during replay (E7 test).

---

## 8. Segment C — meta_mutator_llm default + deterministic fallback offline (P4-002, P4-007)

### 8.1 Objective

Live meta mutation uses **Cursor LLM unified diffs** against real whitelisted source. Deterministic constant-insert is **CI/offline only**.

### 8.2 Decision tree (`propose_searcher_patch`)

```
DAEDALUS_META_OFFLINE == "1"?
  YES → _propose_searcher_patch_offline (deterministic_log_conditioned_fallback)
  NO  → propose_searcher_patch_llm(...)
          None? → offline fallback
          MetaPatchProposal with source=llm_log_conditioned
```

### 8.3 LLM path details

| Step | Implementation |
|------|----------------|
| Prompt | `agents/meta_mutator_prompt.build_meta_mutator_prompt` |
| Conditioning | `log_analyzer.MetaProblemStatement`, parent manifest, `MetaPromptDB.champion_directive()` |
| Invocation | `agents/cursor_cli.run_agent_cli` label `meta_mutator` |
| Parse | `agents/mutator_diff.extract_unified_diff` |
| Validate | diff applies to all `target_paths`; content hashes recorded |
| Budget | `min(budget_tokens, META_REPLAY_BUDGET_TOKENS * 0.15)` |

### 8.4 Offline fallback (deterministic)

Patches module-level constants:

- `search/operator_sampler.py` → `_META_EXPLORATION_DEFAULT`
- `search/prompt_sampler.py` → `META_PROMPT_INSPIRATION_K`
- `search/experience_replay.py` → `_META_REPLAY_K`

Labeled `deterministic_log_conditioned_fallback` with `_log.warning`.

### 8.5 Environment matrix

| Env | Expected `patch_source` |
|-----|-------------------------|
| `DAEDALUS_META_OFFLINE=1` | `deterministic_log_conditioned_fallback` |
| Live WSL + Cursor + key | `llm_log_conditioned` |
| Live without Cursor | fallback (logged) |

### 8.6 Operator checklist — Segment C

- [ ] `DAEDALUS_META_OFFLINE=0` in `run_all_generated_campaigns.py` env.
- [ ] `CURSOR_API_KEY` or `HERMES_CURSOR_API_KEY` set in WSL.
- [ ] Campaign stdout includes `meta_mutator_llm: LLM patch source=llm_log_conditioned`.
- [ ] `verify_meta_mutation.py` passes with offline flag for CI.

---

## 9. Segment D — EM epoch scheduling + live campaign meta_ran=true proof (P4-001)

### 9.1 Scheduling (`r38_epoch_controller.py`)

```python
is_meta = epoch_index > 0 and (epoch_index % META_EPOCH_CADENCE == 0)
# META_EPOCH_CADENCE = 2 (default)
```

**Epoch index map (default cadence):**

| Index | Type | Notes |
|-------|------|-------|
| 0 | OP | E0 grounding + rounds |
| 1 | OP | |
| 2 | **META** | First EM — `run_em` → `run_meta_agent_search` |
| 3 | OP | |
| 4 | **META** | Second EM |

### 9.2 Campaign integration

- `campaign.start(max_epochs=6)` → should hit META at 2 and 4 if not halted.
- EM debits ledger: 500 tokens, category `meta`.
- `state.write_counters(em_counter=epoch_index)`.

### 9.3 Required proof artifacts

After successful EM at epoch ≥2:

```json
{
  "meta_ran": true,
  "meta_epochs": [2],
  "searcher_promoted": true,
  "patch_source": "llm_log_conditioned",
  "compile_ok": true,
  "frozen_corpus_size": 8,
  "replay": {
    "candidate": { "n_rounds": 4, "win_vs_champion": true }
  },
  "repo_patch_applied": false
}
```

### 9.4 Campaign summary enhancement (implementation note)

Add to `campaign._summary`:

```python
"meta_ran": any(r.is_meta for r in results),
"meta_accepted": sum(r.accepted for r in results if r.is_meta),
```

Aligns `RUN_GAPS.JSON run_status.meta_ran` with actual execution.

### 9.5 phase_journal entries for META

At EM boundary, append:

```json
{
  "phase": "epoch_complete",
  "epoch": 2,
  "target": "META",
  "searcher_promoted": true,
  "patch_source": "llm_log_conditioned",
  "frozen_corpus_size": 8,
  "gap_refs": []
}
```

### 9.6 Live run command

```bash
cd daedalus
export HERMES_CURSOR_EXECUTION=wsl_native
export DAEDALUS_SEARCH_MODE=archive
export DAEDALUS_META_MODE=agent_search
export DAEDALUS_META_OFFLINE=0
export DAEDALUS_META_APPLY_PATCH=0   # journal-only until operator approves
python verification/live/run_all_generated_campaigns.py --target simple_rsi_strategy
```

**Precondition:** FIX_1–4 complete; ≥8 journal ACCEPTs; gating AGENT_D profiles resolved for target.

### 9.7 Operator checklist — Segment D

- [ ] Campaign reaches epoch index 2 without killswitch halt.
- [ ] `run_em` diagnostics contain `meta_mode: agent_search`.
- [ ] `meta_ran: true` in final summary.
- [ ] Provenance journal ACCEPT or DISCARD for `operator=META_AGENT_SEARCH`.
- [ ] If promoted: `apply_champion_for_op_epoch` runs at next OP epoch start.

---

## 10. Segment E — Whitelist phased expansion + champion_apply policy fields (P4-006, P4-T001)

### 10.1 Whitelist phases (detailed)

**Phase Day-1 (current default)**

Paths: `search/operator_sampler.py`, `search/prompt_sampler.py`, `search/experience_replay.py`

Regression: `verify_meta_mutation` M001 sandbox compile + import `PromptSampler`.

**Phase Day-2**

Add: `learned/ucb_bandit.py`, `agents/mutator_prompt.py`

Regression: mini-OP replay accept_rate not worse than champion baseline on frozen corpus.

**Phase Day-3 (engine self-edit)**

Add when `META_ALLOW_ENGINE_SELF_EDIT=1`: `search/parent_sampler.py`, `search/program_database.py`

Regression: dedicated tests for DGM parent_weight ordering under patched parent_sampler; human R40 signoff required.

**Denylist (never):** `gate/`, `metric/`, `frozen/`, `governance/`, R29, R39, R30, R33 modules per `META_DENYLIST_PATHS`.

### 10.2 champion_apply — what OP actually reads

`apply_champion_for_op_epoch()` returns:

```python
{
  "exploration_c": float,      # → ProposalEngine / OperatorSampler
  "parent_temperature": float, # → ParentSampler categorical flattening
  "policy_id": str,
  "gnn_weights_applied": bool,
}
```

`apply_searcher_code_patch()` — when `DAEDALUS_META_APPLY_PATCH=1`:

- Applies unified diff to live repo whitelisted files.
- Journals to `state/meta/searcher_patch_journal.jsonl`.

### 10.3 P4-T001 — Wire or prune dormant policy fields

**Stored but unused in OP spine:**

| Field | Stored in | Proposed wiring |
|-------|-----------|-----------------|
| `explore_probability` | `champion_policy.json` | `OperatorSampler` exploration mix vs exploit |
| `thompson_scale` | manifest | Thompson sampling arm variance |
| `entropy_bonus` | manifest | Site diversity bonus in `proposal_engine._resolve_site` |
| `step_size`, `step_decay` | manifest | GNN surrogate online update bounds |

**Rule:** Either wire through `proposal_engine.propose(..., temperature=...)` and operator sampler in Segment E implementation, or strip from `MetaPolicyManifest.to_r31_manifest` to prevent theater.

### 10.4 Meta prompt DB (P4-009 / AlphaEvolve)

`MetaPromptDB.champion_directive()` feeds LLM meta mutator. Co-evolution loop:

1. Meta mutator invents / selects prompt variant.
2. Downstream OP epoch measures accept rate.
3. `prompt_db.evaluate_champion()` updates champion directive.

### 10.5 Operator checklist — Segment E

- [ ] Document active whitelist in campaign env `DAEDALUS_META_WHITELIST`.
- [ ] After promotion, next OP epoch logs `exploration_c` and `parent_temperature` from champion.
- [ ] Audit `champion_policy.json` — no orphan fields without OP effect.
- [ ] `searcher_patch_journal.jsonl` reviewed before setting `DAEDALUS_META_APPLY_PATCH=1`.

---

## 11. Safety stack (non-negotiable)

Meta mutation is gate-adjacent. Full stack in `meta_agent_search`:

| Gate | Tool | Purpose |
|------|------|---------|
| Boundary | `MetaSafety.validate_boundary` | Whitelist-only paths; deny gate/metric/frozen |
| R33 | `MetaSafety.real_r33` | AST compare — no whitelist widening |
| M006 | `compile_capability_filter` | Patched searcher imports and compiles |
| R30 | `GateIntegritySuperGate` | Human signoff if gate-touch attempted |
| R51 | `ShadowAB` | Counterfactual vs champion replay |
| R31 | `MetaBenchmark` | Meta score non-regression |
| Capability | `capability_tripwire` | Single-epoch jump ceiling `META_CAPABILITY_CEILING` |
| Budget | R52 token wall | `META_REPLAY_BUDGET_TOKENS` |

**Threat model** (from `meta_agent_search._THREAT_MODEL`):

1. Overfit frozen corpus → E5 hash-lock + bootstrap held-out.
2. Boundary widening → R33 AST+regex.
3. Broken searcher → M006 compile filter.
4. Eval log tampering → R29/R30 deny-list never whitelisted.
5. Budget exhaustion → R52 token wall.

---

## 12. Cross-dependencies

### 12.1 FIX_1–4 (must complete first)

```
FIX_1 (P1 archive/parent) ──► journal ACCEPTs with real parents
FIX_2 (P2 mutation context) ──► diverse sites/operators in journal
FIX_3 (P3 co-evolution) ──► lessons optional but improves log_analyzer
FIX_4 (gating E2E) ──► valid rewards in journal for corpus freeze
         │
         ▼
FIX_5 (P4 meta) ──► EM epoch with ≥8 task corpus + LLM patch + replay win
```

### 12.2 Gating AGENT_D

Per `daedalus/agent_prompts/gating/00_ORCHESTRATION.md`:

- **AGENT_D** — RSI diagnostics + meta gate policy (G6-meta).
- Meta promotion must respect resolved gate profiles from operator policy.
- Measurement monopoly: meta replay scores from harness, not mutator stdout.

### 12.3 P5 demotion

GNN retrain in `em_meta._run_em_agent_search` is **OutcomePrior advisory only** — does not override replay promotion decision.

---

## 13. Verification matrix

| ID | Check | Script |
|----|-------|--------|
| M001 | Real diff on whitelisted source | `verify_meta_mutation.py` |
| M002 | mini_op_replay n_rounds > 0 | same |
| M006 | Broken patch rejected | same |
| M007 | log_analyzer problem statement | same |
| P4-003 | No `_gate_journal_only` | same |
| P4-004 | Corpus ≥8 hash-locked | same |
| P4-007 | Mock LLM path | same |
| S001 | No synthetic promotion diff | same |
| S002 | Honest promotion message | same |
| B003 | Parent manifest affects mutation | same |
| E7 | Replay isolated from live state | same |
| P4-T002 | `DAEDALUS_LEGACY_META` gate | same |

**Full suite:**

```bash
cd daedalus
python verification/verify_meta_mutation.py
python verification/run_all_daedalus_verifications.py
```

Exit 0 required before declaring FIX_5 complete.

---

## 14. Implementation sequence (recommended)

1. **Segment A** — Confirm freeze at campaign boot; validate journal diversity from FIX_1–4 run.
2. **Segment C** — Enable LLM path in live env; smoke test `patch_source=llm_log_conditioned`.
3. **Segment B** — Confirm `n_rounds > 0` in EM diagnostics.
4. **Segment D** — Run full campaign to epoch 2+; capture `meta_ran=true`.
5. **Segment E** — Wire policy fields or prune; expand whitelist per phase gates.
6. **P4-005** — Operator review; optional `DAEDALUS_META_APPLY_PATCH=1`.
7. **P4-008/009** — Deferred after live proof.

---

## 15. Success criteria (Definition of Done)

FIX_5 is **done** when ALL hold:

1. `python verification/verify_meta_mutation.py` exits 0.
2. `python verification/run_all_daedalus_verifications.py` exits 0.
3. Live campaign completes EM at epoch index ≥2.
4. `run_status.meta_ran=true` (or campaign summary equivalent).
5. `frozen_corpus_size >= 8` from real journal, not bootstrap-only.
6. At least one meta attempt with `patch_source=llm_log_conditioned`.
7. `replay.candidate.n_rounds > 0` on promoted or best discard.
8. `compile_ok` reported truthfully.
9. Champion policy applied to subsequent OP epoch (`exploration_c`, `parent_temperature` logged).
10. `RUN_GAPS.JSON` RG-D001–D005 marked resolved with live evidence links.

---

## 16. References

- `daedalus/MISSING.JSON` → `phase_4_meta_rsi`
- `daedalus/RUN_GAPS.JSON` → `gaps.meta_rsi`, `agent_assignments.D_meta_rsi`
- `daedalus/GATING+METRICS_Plan.md` v2.1 — agent proposes, Python disposes
- `daedalus/agent_prompts/gating/AGENT_D_META_RSI.md` — G6-meta gate policy
- `06_DAEDALUS_RSI_Architecture (7).md` — epoch map EM
- DGM arXiv:2505.22954 §C.2–C.3
- ADAS arXiv:2408.08435
- AlphaEvolve arXiv:2506.13131 — meta-prompt DB co-evolution

---

## 17. Appendix — Key function entry points

### `run_meta_agent_search` (abbreviated flow)

1. `freeze_eval_corpus_snapshot` → `_frozen_corpus_from_snapshot`
2. `MetaArchive.sample_parent` → `_load_parent_manifest`
3. `run_mini_op_replay(patched_sandbox=None)` — champion baseline
4. `analyze_meta_logs` — DGM problem statement
5. `propose_searcher_patch` — LLM or offline
6. `MetaSafety.validate_boundary`, `real_r33`, `compile_capability_filter`
7. `run_mini_op_replay(patched_sandbox=sandbox_root)` — candidate
8. Promotion decision → optional `apply_searcher_code_patch`, `save_champion`

### `run_em` agent_search branch

1. `rebuild_from_journal()` — refresh historical corpus file (not frozen snapshot)
2. `run_meta_agent_search(epoch_index=...)`
3. R30/R33/capability escalation checks
4. GNN retrain (advisory)
5. Journal `META_AGENT_SEARCH` record
6. Return `EpochResult(is_meta=True)`

---

*End of FIX_5 charter — Meta-RSI Searcher Self-Improvement*
