"""P5 — Horizon Refresh & Reconciliation (doc 02 §12)."""

from __future__ import annotations

from config.loop_config import is_dry_run, is_skip_cursor
from orchestrator.bootstrap import HermesContext
from tools.common import Phase


def run_phase5(ctx: HermesContext, state: dict, *, reason: str) -> dict:
    print(f"[P5] Horizon Refresh - reason={reason}")

    contested = [
        s.get("step_id")
        for s in state.get("master_plan", [])
        if s.get("status") in ("contested", "blocked")
    ]
    if contested:
        state = ctx.horizon.select_window(state, forced_lookback_step=contested[0])
    else:
        state = ctx.horizon.mark_wipe_due(state)

    ctx.ast_mapper.build_map()
    meta = ctx.ast_mapper.meta_summary()
    print(f"[P5] {meta}")

    objective = (state.get("core_objective") or {}).get("text", "")
    if not ctx.objective_verifier.verify(state):
        state = ctx.objective_verifier.restore_if_tampered(state)

    proposed = list(state.get("master_plan", []))
    guard = ctx.mutation_guard.validate_mutation(
        state,
        proposed,
        justification=f"P5 reconcile: {reason}",
        delta_reason="SCOPE_CLARIFICATION",
        repo_root=ctx.repo_root,
    )
    if guard.ok:
        diff_hash = guard.data["proposed_diff_sha256"]
        approved = diff_hash
        apply_mutation = is_dry_run()
        delta_reason = "SCOPE_CLARIFICATION"
        stage2_only_ok = delta_reason in {"SCOPE_CLARIFICATION", "DEPENDENCY_REORDER"}
        gate = ctx.cursor_gate.run(skip=is_skip_cursor())
        if gate.status.value == "CURSOR_OK" and not is_dry_run():
            try:
                v = ctx.agent_reviewer.verify_plan(
                    repo_root=ctx.repo_root,
                    objective=objective,
                    current_plan=state.get("master_plan", []),
                    proposed_plan=guard.data["proposed_plan"],
                    diff_sha256=diff_hash,
                )
                if v.verdict == "APPROVE" and v.approved_diff_sha256 == diff_hash:
                    approved = v.approved_diff_sha256
                    apply_mutation = True
            except Exception as exc:
                if stage2_only_ok:
                    print(
                        f"[P5] T10 co-verify failed ({exc}) - "
                        "Stage-2 deterministic fallback (doc SS4.4)"
                    )
                    approved = diff_hash
                    apply_mutation = True
                else:
                    ctx.escalation.alert(f"Cursor co-verify error at P5: {exc}", state)
                    raise
        elif gate.status.value != "CURSOR_OK" and not is_dry_run():
            if stage2_only_ok:
                print(
                    f"[P5] Cursor unavailable ({gate.reason_code}) - "
                    "proceeding on T04 Stage-2 validation only (SCOPE_CLARIFICATION)"
                )
                approved = diff_hash
                apply_mutation = True
            else:
                ctx.escalation.alert(
                    f"Cursor unavailable for P5 reconcile: {gate.reason_code}", state
                )
                raise RuntimeError(gate.detail)
        if apply_mutation:
            state = ctx.state_manager.write_plan_mutation(
                state, guard.data["proposed_plan"], approved_diff_sha256=approved
            )

    if ctx.cycle_detector.record_phase_transition(state, Phase.P5.value, None):
        ctx.escalation.alert("Oscillation detected in P5", state)

    if ctx.horizon.project_complete(state):
        runtime = dict(state.get("runtime") or {})
        runtime["current_phase"] = "DONE"
        state = ctx.state_manager.write_runtime_field(state, "runtime", runtime)
        print("[P5] Project complete")
        return ctx.state_manager.read()

    if not ctx.budget.preflight_floor_clear(state):
        ctx.escalation.alert("Budget floor at P5", state)
        return state

    state = ctx.horizon.select_window(state, git_ref="work@reconcile")
    state = ctx.state_manager.write_runtime_field(state, "horizon", state["horizon"])
    runtime = dict(state.get("runtime") or {})
    runtime["current_phase"] = Phase.P5.value
    state = ctx.state_manager.write_runtime_field(state, "runtime", runtime)
    return ctx.state_manager.read()
