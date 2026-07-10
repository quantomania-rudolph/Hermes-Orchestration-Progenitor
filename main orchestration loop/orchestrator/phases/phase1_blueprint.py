"""P1 — Blueprint & Horizon (doc 02 §8)."""

from __future__ import annotations

from config.loop_config import is_dry_run, is_skip_cursor
from orchestrator.bootstrap import HermesContext
from tools.common import Phase, SystemHalt
from tools.context.t07_rag_provisioner import RAGQueryInput


def run_phase1(ctx: HermesContext, state: dict) -> dict:
    print("[P1] Blueprint & Horizon")
    ctx.phase_controller.transition(state, Phase.P0, Phase.P1)

    if not ctx.budget.preflight_floor_clear(state):
        ctx.escalation.alert("Budget pre-flight floor not met (T21)", state)
        raise SystemHalt("Cannot open horizon window - budget floor")

    proposed_plan = list(state.get("master_plan", []))
    guard = ctx.mutation_guard.validate_mutation(
        state,
        proposed_plan,
        justification="Horizon window from user-seeded plan",
        delta_reason="SCOPE_CLARIFICATION",
        repo_root=ctx.repo_root,
    )
    if not guard.ok:
        raise SystemHalt(guard.message)

    proposed_plan = guard.data["proposed_plan"]
    diff_hash = guard.data["proposed_diff_sha256"]
    approved_hash = diff_hash

    gate = ctx.cursor_gate.run(budget_ok=True, skip=is_skip_cursor())
    delta_reason = "SCOPE_CLARIFICATION"
    stage2_only_ok = delta_reason in {"SCOPE_CLARIFICATION", "DEPENDENCY_REORDER"}

    if gate.status.value == "CURSOR_OK" and not is_dry_run():
        objective = (state.get("core_objective") or {}).get("text", "")
        try:
            verdict = ctx.agent_reviewer.verify_plan(
                repo_root=ctx.repo_root,
                objective=objective,
                current_plan=state.get("master_plan", []),
                proposed_plan=proposed_plan,
                diff_sha256=diff_hash,
            )
            if verdict.verdict != "APPROVE" or verdict.approved_diff_sha256 != diff_hash:
                ctx.escalation.alert(f"Plan co-verify REJECT: {verdict.reason}", state)
                raise SystemHalt(f"Plan co-verify failed: {verdict.reason}")
            approved_hash = verdict.approved_diff_sha256
        except Exception as exc:
            if stage2_only_ok:
                print(f"[P1] T10 co-verify failed ({exc}) - Stage-2 deterministic fallback (doc SS4.4)")
                approved_hash = diff_hash
            else:
                ctx.escalation.alert(f"Cursor co-verify error: {exc}", state)
                raise SystemHalt(str(exc)) from exc
    elif gate.status.value != "CURSOR_OK" and not is_dry_run():
        if stage2_only_ok:
            print(
                f"[P1] Cursor unavailable ({gate.reason_code}) - "
                "proceeding on T04 Stage-2 validation only (SCOPE_CLARIFICATION)"
            )
            approved_hash = diff_hash
        else:
            ctx.escalation.alert(f"Cursor unavailable for plan co-verify: {gate.reason_code}", state)
            raise SystemHalt(gate.detail)

    state = ctx.state_manager.write_plan_mutation(
        state, proposed_plan, approved_diff_sha256=approved_hash
    )
    if not ctx.objective_verifier.verify(state):
        state = ctx.objective_verifier.restore_if_tampered(state)

    rag = ctx.rag.run(
        RAGQueryInput(
            query="horizon window master plan pipeline_state HERMES phases tools",
            phase=Phase.P1.value,
            top_k=5,
        )
    )
    if rag.ok:
        print(
            f"[P1] RAG: {rag.data.get('codebase_hits', 0)} codebase hit(s), "
            f"{len(rag.data.get('doc_snippets', []))} doc snippet(s)"
        )

    state = ctx.horizon.select_window(state, git_ref="work@genesis")
    state = ctx.state_manager.write_runtime_field(state, "horizon", state["horizon"])
    runtime = dict(state.get("runtime") or {})
    runtime["current_phase"] = Phase.P1.value
    state = ctx.state_manager.write_runtime_field(state, "runtime", runtime)

    ctx.phase_controller.assert_exit(state, Phase.P0, Phase.P1)
    print(f"[P1] Horizon window: {(state.get('horizon') or {}).get('window')}")
    return ctx.state_manager.read()
