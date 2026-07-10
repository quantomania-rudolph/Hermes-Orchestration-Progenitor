"""P2 — Implementation & Reference (full gauntlet per doc 02 §9)."""

from __future__ import annotations

from config.loop_config import cursor_runtime, is_dry_run, is_skip_cursor, t09_runtime
from orchestrator.bootstrap import HermesContext
from orchestrator.gauntlet import run_p2_gauntlet
from tools.common import Phase, SystemHalt
from tools.context.t07_rag_provisioner import RAGQueryInput


class Phase2Result:
    SUCCESS = "SUCCESS"
    DEVIATION = "DEVIATION"
    CURSOR_DOWN = "CURSOR_DOWN"


def run_phase2_step(ctx: HermesContext, state: dict, step_id: str) -> tuple[dict, str]:
    print(f"[P2] Implementation - step {step_id}")
    step = next((s for s in state.get("master_plan", []) if s.get("step_id") == step_id), None)
    if not step:
        raise SystemHalt(f"Step {step_id} not found")

    ctx.ast_mapper.build_map()
    gate = ctx.cursor_gate.run(
        budget_ok=ctx.budget.preflight_floor_clear(state),
        skip=is_skip_cursor(),
    )
    cursor_ok = gate.status.value == "CURSOR_OK"

    auth = ctx.boundary_compiler.compile_step(step, ctx.repo_root)
    interfaces = ctx.ast_mapper.inject_interfaces(step.get("target_files", []))
    rag = ctx.rag.run(
        RAGQueryInput(
            query=ctx.rag.build_step_query(step),
            phase=Phase.P2.value,
            top_k=5,
        )
    )
    if rag.ok:
        hits = rag.data.get("codebase_hits", 0)
        docs = len(rag.data.get("doc_snippets", []))
        print(f"[P2] RAG: {hits} codebase hit(s), {docs} doc snippet(s)")
    objective = (state.get("core_objective") or {}).get("text", "")
    wrapped = ctx.objective_envelope.wrap(
        state,
        subtask=step.get("intent", step.get("title", "")),
        context_data=(rag.data.get("codebase_context", "") if rag.ok else "")[:4000],
    )

    target_files = list(step.get("target_files", []))
    snap = ctx.git_snapshot.take_snapshot(ctx.repo_root, target_files)

    files_exist = all((ctx.repo_root / tf).is_file() for tf in target_files) if target_files else False
    generated = False

    if is_dry_run():
        print("[P2] DRY_RUN: Cursor/Qwen spawns skipped; running Python gauntlet on current tree")
    elif t09_runtime() in {"auto", "cursor", "qwen"}:
        creator_result, delegate = ctx.agent_creator.run_with_fallback(
            repo_root=ctx.repo_root,
            objective=objective,
            step_intent=step.get("intent", ""),
            auth=auth,
            interfaces=interfaces,
            rag_context=rag.data.get("codebase_context", "") if rag.ok else "",
            target_files=target_files,
            wrapped_prompt=wrapped,
            cursor_ok=cursor_ok,
        )
        if creator_result and creator_result.ok:
            generated = True
            print(f"[P2] T09 generation OK via {delegate}")
            from agents.sync_barrier import wait_for_files

            try:
                barrier_timeout = 180.0 if cursor_runtime() in {"cloud", "auto"} else 30.0
                wait_for_files(ctx.repo_root, target_files, timeout_sec=barrier_timeout)
            except Exception as exc:
                print(f"[P2] Sync barrier: {exc} (infrastructure, no strike)")

            if delegate == "cursor" and cursor_ok:
                gate2 = ctx.cursor_gate.run(budget_ok=True)
                if gate2.status.value == "CURSOR_OK":
                    arch = ""
                    if ctx.semantic.architecture_md.is_file():
                        arch = ctx.semantic.architecture_md.read_text(encoding="utf-8")[:3000]
                    diff_sum = ctx.diff_analyzer.diff_summary(ctx.repo_root, target_files)
                    try:
                        ctx.agent_reviewer.review_code(
                            repo_root=ctx.repo_root,
                            step_intent=step.get("intent", ""),
                            auth=auth,
                            diff_summary=diff_sum,
                            architecture_excerpt=arch,
                        )
                    except Exception as exc:
                        print(f"[P2] T10 review skipped (infra): {exc}")
        elif not files_exist:
            print(f"[P2] T09 failed — no files on disk (cursor_ok={cursor_ok}, mode={t09_runtime()})")
            return state, Phase2Result.CURSOR_DOWN
        else:
            print("[P2] T09 skipped/failed — using existing files on disk")
    elif files_exist:
        print(f"[P2] Cursor unavailable ({gate.reason_code}) - files exist, running gauntlet")
    else:
        print(f"[P2] Cursor unavailable ({gate.reason_code}) - cannot run T09")
        return state, Phase2Result.CURSOR_DOWN

    code_summary = ctx.diff_analyzer.diff_summary(ctx.repo_root, target_files)
    gauntlet = run_p2_gauntlet(
        ctx,
        repo_root=ctx.repo_root,
        boundaries=auth.boundaries,
        target_files=target_files,
        wrapped_prompt=wrapped,
        code_summary=code_summary,
    )
    if not gauntlet.ok:
        ctx.git_snapshot.restore(ctx.repo_root, snap)
        state, count = ctx.strike_breaker.record_strike(
            state, target_files[0] if target_files else step_id, gauntlet.stage
        )
        state = ctx.state_manager.write_runtime_field(state, "strike_ledger", state["strike_ledger"])
        if ctx.strike_breaker.is_strikeout(count):
            ctx.escalation.alert(f"Strike-out at {gauntlet.stage}", state)
            raise SystemHalt(f"Three-strikes at {gauntlet.stage}")
        raise SystemHalt(f"P2 gauntlet failed at {gauntlet.stage}: {gauntlet.detail}")

    state = ctx.state_manager.write_step_status(state, step_id, "implemented")
    runtime = dict(state.get("runtime") or {})
    runtime["current_phase"] = Phase.P2.value
    state = ctx.state_manager.write_runtime_field(state, "runtime", runtime)
    state = ctx.budget.record_usage(state, tokens=500, usd=0.01)
    state = ctx.state_manager.write_runtime_field(state, "budget", state["budget"])
    return ctx.state_manager.read(), Phase2Result.SUCCESS
