# HERMES Main Orchestration Loop — Architecture Rubric (T13)

Human-authored semantic contract. T13 parses machine-readable markers below.

<!-- T13:async_patterns -->
- Prefer async I/O for network and database boundaries when the target stack supports it.
- Do not block the orchestration loop on long-running model calls without timeout guards.

<!-- T13:naming_conventions -->
- Python modules: snake_case filenames matching tool IDs (e.g. `t03_pipeline_state_manager.py`).
- Tool classes expose a single `run()` method with typed input/output dataclasses.
- Phase modules export `run_phaseN()` only; no cross-phase imports.

<!-- T13:state_ownership -->
- Only T03 writes `pipeline_state.json`. All other modules read via T03.read().
- Runtime fields (`horizon`, `budget`, `strike_ledger`, `journal`, `wal`) are Python-only writes.

<!-- T13:index_consistency -->
- T07 must call the parent `build_index.py` for builds and reindexes.
- After P4 merge or any Cursor write set, run incremental reindex before the next P2 step.
- Index is consistent when `file_mtimes` in `codebase_vectors.json` matches on-disk mtimes.

<!-- T13:hermes_proposes_python_disposes -->
- Hermes (local Qwen) proposes plan diffs and tool calls inside forced schemas.
- Python validates, gates by phase, and executes. Models never write state directly.
