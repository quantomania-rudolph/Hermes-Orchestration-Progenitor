"""P3 — Audit & Verification (doc 02 §10)."""

from __future__ import annotations

from orchestrator.bootstrap import HermesContext
from orchestrator.gauntlet import run_p2_gauntlet
from tools.common import Phase, SystemHalt


class Phase3Result:
    GREEN = "GREEN"
    PLAN_OMISSION = "PLAN_OMISSION"
    BLOCKED = "BLOCKED"


def run_phase3_step(ctx: HermesContext, state: dict, step_id: str) -> tuple[dict, str]:
    print(f"[P3] Audit - step {step_id}")
    step = next((s for s in state.get("master_plan", []) if s.get("step_id") == step_id), None)
    if not step:
        raise SystemHalt(f"Step {step_id} not found")

    test = ctx.test_runner.run_tests(ctx.repo_root)
    fuzz = ctx.fuzzer.run_against_schemas(ctx.loop_dir / "docs" / "schemas")

    if test.ok and fuzz.ok:
        state = ctx.state_manager.write_step_status(state, step_id, "verified")
        runtime = dict(state.get("runtime") or {})
        runtime["current_phase"] = Phase.P3.value
        state = ctx.state_manager.write_runtime_field(state, "runtime", runtime)
        return ctx.state_manager.read(), Phase3Result.GREEN

    raw = test.output if not test.ok else "\n".join(fuzz.crashes)
    norm = ctx.error_normalizer.normalize(raw)
    triage = ctx.triage.classify(
        ctx.objective_envelope.wrap(state, "triage failure", norm.signature),
        norm.signature,
    )

    if triage.kind == "INFRA_EVENT":
        print("[P3] Infrastructure error - purge and retry (no strike)")
        ctx.test_runner.local_state_purge(ctx.repo_root)
        retry = ctx.test_runner.run_tests(ctx.repo_root)
        if retry.ok:
            state = ctx.state_manager.write_step_status(state, step_id, "verified")
            return ctx.state_manager.read(), Phase3Result.GREEN
        ctx.escalation.alert("Persistent infra failure", state)
        raise SystemHalt("Infrastructure error persists")

    state, strikes = ctx.strike_breaker.record_strike(
        state,
        step.get("target_files", ["?"])[0],
        norm.hash,
    )
    state = ctx.state_manager.write_runtime_field(state, "strike_ledger", state["strike_ledger"])
    if ctx.strike_breaker.is_strikeout(strikes):
        return state, Phase3Result.BLOCKED

    if triage.classification == "PLAN_OMISSION":
        for s in state.get("master_plan", []):
            if s.get("step_id") == step_id:
                s["status"] = "contested"
        state = ctx.state_manager.write_runtime_field(state, "master_plan", state["master_plan"])
        return ctx.state_manager.read(), Phase3Result.PLAN_OMISSION

    # CODE_BUG: localized patch via T10 if Cursor available
    gate = ctx.cursor_gate.run(budget_ok=ctx.budget.preflight_floor_clear(state))
    if gate.status.value == "CURSOR_OK":
        auth = ctx.boundary_compiler.compile_step(step, ctx.repo_root)
        snap = ctx.git_snapshot.take_snapshot(ctx.repo_root, step.get("target_files", []))
        arch = ""
        if ctx.semantic.architecture_md.is_file():
            arch = ctx.semantic.architecture_md.read_text(encoding="utf-8")[:2000]
        ctx.agent_reviewer.review_code(
            repo_root=ctx.repo_root,
            step_intent=step.get("intent", ""),
            auth=auth,
            diff_summary=ctx.diff_analyzer.diff_summary(ctx.repo_root, step.get("target_files", [])),
            architecture_excerpt=arch,
            failing_trace=raw[:3000],
        )
        wrapped = ctx.objective_envelope.wrap(state, "post-patch gauntlet", "")
        g = run_p2_gauntlet(
            ctx,
            repo_root=ctx.repo_root,
            boundaries=auth.boundaries,
            target_files=step.get("target_files", []),
            wrapped_prompt=wrapped,
            code_summary="patch",
        )
        if not g.ok:
            ctx.git_snapshot.restore(ctx.repo_root, snap)

    ctx.test_runner.local_state_purge(ctx.repo_root)
    retry = ctx.test_runner.run_tests(ctx.repo_root)
    if retry.ok:
        state = ctx.state_manager.write_step_status(state, step_id, "verified")
        return ctx.state_manager.read(), Phase3Result.GREEN

    return ctx.state_manager.read(), Phase3Result.BLOCKED
