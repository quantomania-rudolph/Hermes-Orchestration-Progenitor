"""P4 — Integration & Commit (doc 02 §11)."""

from __future__ import annotations

import json

from orchestrator.bootstrap import HermesContext
from tools.common import Phase, SystemHalt


class Phase4Result:
    GREEN = "GREEN"
    BRANCH_DRIFT = "BRANCH_DRIFT"


def run_phase4_step(ctx: HermesContext, state: dict, step_id: str) -> tuple[dict, str]:
    print(f"[P4] Integration - step {step_id}")
    step = next((s for s in state.get("master_plan", []) if s.get("step_id") == step_id), None)
    if not step:
        raise SystemHalt(f"Step {step_id} not found")

    auth = ctx.boundary_compiler.compile_step(step, ctx.repo_root)
    horizon_snap = {}
    import config.loop_config as loop_config

    if loop_config.HORIZON_OPEN_PATH.is_file():
        horizon_snap = json.loads(loop_config.HORIZON_OPEN_PATH.read_text(encoding="utf-8"))

    double = ctx.diff_analyzer.double_diff_audit(
        ctx.repo_root, auth.boundaries, horizon_snap
    )
    if not double.ok:
        raise SystemHalt(f"T14 double-diff failed: {double.violations}")

    state = ctx.journal.write_intent_to_integrate(state, step_id)
    state = ctx.state_manager.write_runtime_field(state, "wal", state["wal"])

    expected = horizon_snap.get("git_ref")
    if not ctx.git_snapshot.fast_forward_valid(ctx.repo_root, expected):
        state = ctx.journal.clear_intent_to_integrate(state)
        for s in state.get("master_plan", []):
            if s.get("step_id") == step_id:
                s["status"] = "contested"
        state = ctx.state_manager.write_runtime_field(state, "master_plan", state["master_plan"])
        return ctx.state_manager.read(), Phase4Result.BRANCH_DRIFT

    ctx.git_snapshot.merge_scratch(ctx.repo_root)
    reindex = ctx.rag.reindex_after_merge()
    ctx.ast_mapper.build_map()
    print(f"[P4] Reindex: {reindex.message}")

    runtime = dict(state.get("runtime") or {})
    index = dict(runtime.get("index") or {})
    index["last_build_at"] = reindex.data.get("built_at")
    index["consistent"] = reindex.ok
    runtime["index"] = index
    runtime["current_phase"] = Phase.P4.value
    state = ctx.state_manager.write_runtime_field(state, "runtime", runtime)

    state = ctx.state_manager.write_green_commit(state, step_id)
    state = ctx.journal.clear_intent_to_integrate(state)
    state = ctx.state_manager.write_runtime_field(state, "wal", state["wal"])
    print(f"[P4] Step {step_id} green")
    return ctx.state_manager.read(), Phase4Result.GREEN
