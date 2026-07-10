"""P0 — Genesis & Grounding."""

from __future__ import annotations

from pathlib import Path

import config.loop_config as loop_config
from orchestrator.bootstrap import HermesContext
from tools.common import Phase, SystemHalt
from tools.governance.output_paths import bind_generated_output
from tools.safety.t23_state_journal import RecoveryAction


def run_phase0(
    ctx: HermesContext,
    *,
    seed_path: Path,
    repo_path: Path,
) -> dict:
    print("[P0] Genesis & Grounding")

    recovery = ctx.journal.detect_interrupted_run(None)
    if loop_config.PIPELINE_STATE_PATH.is_file():
        state = ctx.state_manager.read()
        recovery = ctx.journal.detect_interrupted_run(state)
        print(f"[P0] Existing state detected - recovery action: {recovery.value}")
    else:
        state = ctx.state_manager.ingest_seed(seed_path)
        state = bind_generated_output(state, repo_path)
        recovery = RecoveryAction.FRESH_START

    state = ctx.objective_verifier.lock_objective(state)
    state = ctx.mutation_guard.capture_genesis_baseline(state)
    state = ctx.budget.initialize(state)

    ctx.ast_mapper.build_map()
    index_result = ctx.rag.initialize_at_genesis(full_if_missing=True)
    if not index_result.ok:
        ctx.escalation.alert("P0 index build failed", state, extra=index_result.data)
        raise SystemHalt(index_result.message)

    cursor = ctx.cursor_gate.run(
        budget_ok=ctx.budget.preflight_floor_clear(state),
        skip=loop_config.is_skip_cursor() or loop_config.is_dry_run(),
    )
    print(f"[P0] Cursor preflight: {cursor.status.value} - {cursor.detail}")

    runtime = dict(state.get("runtime") or {})
    runtime["current_phase"] = Phase.P0.value
    runtime["repo_path"] = str(repo_path)
    chunk_count = index_result.data.get("chunk_count", 0)
    if not chunk_count:
        try:
            chunk_count = len(ctx.index_bridge.load_chunks())
        except (FileNotFoundError, ValueError):
            chunk_count = 0
    runtime["index"] = {
        "vectors_path": str(ctx.index_bridge.vectors_path),
        "last_build_at": index_result.data.get("built_at"),
        "last_consistency_check_at": index_result.data.get("built_at"),
        "consistent": index_result.data.get("reused_existing", index_result.ok),
        "chunk_count": chunk_count,
    }
    state["runtime"] = runtime
    state["tool_registry_version"] = ctx.registry.version

    state = ctx.journal.journal_transition(
        state,
        phase=Phase.P0.value,
        step_id=None,
        transition_type="P0_COMPLETE",
        payload={"recovery": recovery.value, "index": runtime["index"]},
    )
    state = ctx.state_manager.write_runtime_field(state, "runtime", runtime)
    print("[P0] Exit contract met -> ready for P1")
    return ctx.state_manager.read()
