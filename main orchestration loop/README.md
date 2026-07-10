# HERMES Main Orchestration Loop

Full implementation of the autonomous software factory per:

- `01_HERMES_Tool_Registry` — all **30 tools** (T01–T30)
- `02_HERMES_Semantic_Pipeline` — P0–P5 master loop, axioms, gauntlets
- `03_HERMES_Architecture` — four-layer layout (state / orchestration / models / agents)

**Core law:** Hermes proposes. Python disposes.

---

## Completeness Checklist (vs source docs)

| Requirement | Status |
|-------------|--------|
| 30-tool registry + phase matrix (T25/T27) | Done |
| pipeline_state.json sole writer (T03) | Done |
| Objective hash lock (T02) | Done |
| Plan mutation guard + co-verify (T04/T10) | Done |
| 3-step horizon (T05) | Done |
| AST map + RAG + boundary (T06/T07/T08) | Done |
| Cursor Creator/Reviewer (T09/T10/T11) | Done |
| P2 gauntlet T14→T12→T13 | Done |
| P3 test/fuzz/triage/patch (T16–T20) | Done |
| P4 2PC WAL + reindex (T23/T07) | Done |
| P5 reconcile + AST meta-summary (T06) | Done |
| Index build + consistency bridge | Done |
| Hermes Qwen via NoLlama (models/hermes.py) | Done |
| Verification suite (8 scripts) | All passing |

---

## How to Run

### Prerequisites (parent repo `START_HERE.txt`)

1. NoLlama running (`scripts\run_intel_gpu\01_start_nollama.bat`)
2. RAG index built (`scripts\setup_index\01_build_index.bat`)
3. `CURSOR_API_KEY` set for **live** P2/P1 co-verify

### Commands

```bat
main orchestration loop\run\00_preflight.bat
main orchestration loop\run\01_run_loop_dry.bat      REM test mode (no Cursor credits)
main orchestration loop\run\02_run_loop_live.bat     REM production
main orchestration loop\run\03_resume_loop.bat
```

```bat
python "main orchestration loop\verification\run_all_verifications.py"
```

---

## Architecture (03)

```
main orchestration loop/
├── pipeline_state.seed.json     # User-seeded plan (genesis input)
├── pipeline_state.json          # Living state (T03 only)
├── architecture.md              # T13 rubric
├── config/                      # loop_config, static_tool_registry (30 tools)
├── state/                       # WAL, snapshots, genesis, alerts, ast_map
├── orchestrator/                # session.py master loop, phases, contracts, gauntlet
├── tools/                       # T01–T30 implementations
│   ├── governance/   T01–T05
│   ├── context/      T06–T08 + index_bridge
│   ├── agents/       T09–T11
│   ├── verification/ T12–T20
│   ├── safety/       T20–T23
│   ├── meta/         T24–T25
│   └── orchestration/ T26–T30
├── models/                      # Hermes Qwen, fast classifier, schema contracts
├── agents/                      # Cursor SDK, prompts, sync_barrier
├── docs/schemas/                # T07/T17 fuzz sources
├── system_tools/                # T24 synthesized tools (quarantine/active)
├── run/                         # Windows launchers
└── verification/                # 8-script test suite
```

---

## Index Integration (Build + Consistent)

| Component | Path | When |
|-----------|------|------|
| Build index | `scripts/setup_index/build_index.py` | P0, P4 |
| Vectors | `codebase_vectors.json` | T07 queries |
| Consistency | `tools/context/index_bridge.py` | Before RAG, after merge |

Scoped to `Hermes_Orchestration` by default (`HERMES_WORKSPACE_ROOTS`).

---

## Phase Flow (02 §5)

```
P0 Genesis    → seed ingest, T02 lock, T06 AST, T07 index, T21 budget, T11 preflight
P1 Blueprint  → T04 guard, T10 co-verify, T05 window, T21 pre-flight
P2 Implement  → T11→T06/T07/T08→T15→T09→sync→T10→T14→T12→T13
P3 Audit      → T16 purge/run, T17 fuzz, infra filter, T19/T18, T10 patch loop
P4 Integrate  → T14 double-diff, T23 2PC, T15 FF, T07 reindex, T06 refresh, T03 green
P5 Reconcile  → state-reset, T06 meta-summary, T04 refine, next window
```

---

## Modes

| Variable | Effect |
|----------|--------|
| `HERMES_DRY_RUN=1` | Skips T09/T10 Cursor spawns; still runs full Python gauntlet |
| `HERMES_SKIP_CURSOR=1` | T11 returns unavailable; P1 uses deterministic co-verify |
| `CURSOR_API_KEY` | Required for live T09/T10/T24 |
| `HERMES_IN_SESSION=1` | Set by session; T16 runs unit tests only (no recursion) |

---

## Production Use

1. Author `pipeline_state.seed.json` with real objective + `master_plan[]`
2. Run dry-run to validate topology
3. Set `CURSOR_API_KEY`, run `02_run_loop_live.bat`
4. Monitor `state/alerts/` and `state/wal.jsonl`
