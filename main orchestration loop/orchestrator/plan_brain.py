"""Hermes plan brain — T26 PLAN_GENERATE/MUTATE + T04/T10/T03 commit path."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from openai import APIConnectionError

from config.loop_config import is_dry_run, is_skip_cursor, is_skip_hermes_brain
from models.schema_contracts.base import SchemaViolation
from models.schema_contracts.plan_mutate import DELTA_REASONS, PlanMutateProposal
from orchestrator.bootstrap import HermesContext
from tools.common import Phase, SystemHalt, sha256_json
from tools.orchestration.t26_model_router import TaskClass


STAGE2_OK = frozenset({"SCOPE_CLARIFICATION", "DEPENDENCY_REORDER"})


def merge_plan_statuses(
    current: list[dict[str, Any]], proposed: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Preserve non-pending statuses when Hermes returns a structural plan update."""
    status_by_id = {s.get("step_id"): s.get("status", "pending") for s in current}
    merged: list[dict[str, Any]] = []
    for step in proposed:
        s = deepcopy(step)
        sid = s.get("step_id")
        prior = status_by_id.get(sid)
        if prior and prior not in ("pending", None):
            s["status"] = prior
        else:
            s.setdefault("status", "pending")
        merged.append(s)
    return merged


def build_plan_prompt(
    ctx: HermesContext,
    state: dict[str, Any],
    *,
    task_class: TaskClass,
    ast_meta: str,
    reason: str,
    strip_horizon: bool,
) -> str:
    view = ctx.horizon.strip_context_for_hermes(state) if strip_horizon else state
    completed = [
        s.get("step_id")
        for s in state.get("master_plan", [])
        if s.get("status") == "green"
    ]
    contested = [
        s.get("step_id")
        for s in state.get("master_plan", [])
        if s.get("status") in ("contested", "blocked")
    ]
    context_blob = json.dumps(
        {
            "task_class": task_class.value,
            "reason": reason,
            "completed_steps": completed,
            "contested_steps": contested,
            "visible_plan": view.get("master_plan", []),
            "full_step_count": len(state.get("master_plan", [])),
        },
        indent=2,
    )[:12000]
    meta_head = (ast_meta or "").splitlines()[0]
    instruction = (
        "Return JSON only with keys: master_plan (full array), justification, "
        f"delta_reason one of {sorted(DELTA_REASONS)}. "
        "Preserve step_id, depends_on, target_files for existing steps. "
        "Preserve status for green/implemented/verified steps. "
        "Do not change core_objective. "
        "Authorized dirs and step count must stay within genesis envelope."
    )
    if task_class == TaskClass.PLAN_MUTATE:
        instruction += (
            " Compare planned vs on-disk reality using AST meta-summary. "
            "Absorb discovered constraints or clarify scope; do not add unmapped features."
        )
    else:
        instruction += " Refine the user-seeded plan for dependency order and clarity."

    return ctx.objective_envelope.wrap(
        state,
        subtask=f"{task_class.value}: {reason}",
        context_data=f"{meta_head}\n\n{context_blob}\n\n{instruction}",
    )


def propose_plan(
    ctx: HermesContext,
    state: dict[str, Any],
    task_class: TaskClass,
    *,
    ast_meta: str,
    reason: str,
    strip_horizon: bool,
    fallback_justification: str,
    force_live: bool = False,
) -> PlanMutateProposal:
    """T26-routed Hermes plan proposal with deterministic fallback."""
    if not force_live and (is_dry_run() or is_skip_hermes_brain()):
        print(f"[T26] {task_class.value} skipped (dry-run or HERMES_SKIP_HERMES_BRAIN) — identity plan")
        return PlanMutateProposal.from_state(
            state,
            justification=fallback_justification,
            delta_reason="SCOPE_CLARIFICATION",
        )

    prompt = build_plan_prompt(
        ctx,
        state,
        task_class=task_class,
        ast_meta=ast_meta,
        reason=reason,
        strip_horizon=strip_horizon,
    )
    try:
        routed = ctx.model_router.route_hermes(
            task_class, prompt, output_schema=PlanMutateProposal
        )
        parsed = getattr(routed.result, "parsed", None)
        if parsed is None and hasattr(routed.result, "raw"):
            parsed = PlanMutateProposal.from_raw(routed.result.raw)
        if not isinstance(parsed, PlanMutateProposal):
            raise SchemaViolation("PLAN proposal missing parsed schema")
        proposal = PlanMutateProposal(
            master_plan=merge_plan_statuses(state.get("master_plan", []), parsed.master_plan),
            justification=parsed.justification,
            delta_reason=parsed.delta_reason,
        )
        print(
            f"[T26] {task_class.value} ok tier={routed.tier} "
            f"steps={len(proposal.master_plan)} delta={proposal.delta_reason}"
        )
        return proposal
    except APIConnectionError as exc:
        if force_live:
            print(
                f"[T26] {task_class.value} brain unreachable (force_live) — "
                f"identity fallback: {exc}"
            )
            return PlanMutateProposal.from_state(
                state,
                justification=fallback_justification,
                delta_reason="SCOPE_CLARIFICATION",
            )
        raise
    except SchemaViolation as exc:
        print(f"[T26] {task_class.value} schema fail: {exc}")
        if task_class == TaskClass.PLAN_MUTATE:
            raise
        choice, _ = ctx.paralysis_breaker.apply_default(
            current_phase=Phase.P1,
            options=["identity_plan"],
            state=state,
        )
        return PlanMutateProposal.from_state(
            state,
            justification=fallback_justification,
            delta_reason="SCOPE_CLARIFICATION",
        )


def is_identity_plan(state: dict[str, Any], proposed: list[dict[str, Any]]) -> bool:
    return sha256_json(state.get("master_plan", [])) == sha256_json(proposed)


def commit_plan_proposal(
    ctx: HermesContext,
    state: dict[str, Any],
    proposal: PlanMutateProposal,
    *,
    phase: Phase,
    skip_co_verify_if_identity: bool = True,
) -> dict[str, Any]:
    """T04 → optional T10 → T03 hash-bound commit."""
    merged_plan = merge_plan_statuses(state.get("master_plan", []), proposal.master_plan)
    proposal = PlanMutateProposal(
        master_plan=merged_plan,
        justification=proposal.justification,
        delta_reason=proposal.delta_reason,
    )
    guard = ctx.mutation_guard.validate_mutation(
        state,
        proposal.master_plan,
        justification=proposal.justification,
        delta_reason=proposal.delta_reason,
        repo_root=ctx.repo_root,
    )
    if not guard.ok:
        raise SystemHalt(guard.message)

    proposed_plan = guard.data["proposed_plan"]
    diff_hash = guard.data["proposed_diff_sha256"]
    approved_hash = diff_hash
    identity = is_identity_plan(state, proposed_plan)
    stage2_ok = proposal.delta_reason in STAGE2_OK

    skip_t10 = skip_co_verify_if_identity and identity and stage2_ok
    if skip_t10:
        print(f"[{phase.value}] Identity plan mutation — skipping T10 co-verify")

    gate = ctx.cursor_gate.run(budget_ok=True, skip=is_skip_cursor())
    if not skip_t10 and gate.status.value == "CURSOR_OK" and not is_dry_run():
        objective = (state.get("core_objective") or {}).get("text", "")
        try:
            verdict = ctx.agent_reviewer.verify_plan(
                repo_root=ctx.repo_root,
                objective=objective,
                current_plan=state.get("master_plan", []),
                proposed_plan=proposed_plan,
                diff_sha256=diff_hash,
            )
            if verdict.verdict == "APPROVE" and verdict.approved_diff_sha256 == diff_hash:
                approved_hash = verdict.approved_diff_sha256
            elif stage2_ok:
                print(
                    f"[{phase.value}] T10 REJECT ({verdict.reason}) — "
                    "Stage-2 fallback for identity/clarification"
                )
                approved_hash = diff_hash
            else:
                ctx.escalation.alert(f"Plan co-verify REJECT at {phase.value}: {verdict.reason}", state)
                raise SystemHalt(f"Plan co-verify failed: {verdict.reason}")
        except Exception as exc:
            if stage2_ok:
                print(f"[{phase.value}] T10 error ({exc}) — Stage-2 deterministic fallback")
                approved_hash = diff_hash
            else:
                ctx.escalation.alert(f"Cursor co-verify error at {phase.value}: {exc}", state)
                raise SystemHalt(str(exc)) from exc
    elif not skip_t10 and gate.status.value != "CURSOR_OK" and not is_dry_run():
        if stage2_ok:
            print(
                f"[{phase.value}] Cursor unavailable ({gate.reason_code}) — "
                "T04 Stage-2 only"
            )
            approved_hash = diff_hash
        else:
            ctx.escalation.alert(
                f"Cursor unavailable for plan co-verify at {phase.value}: {gate.reason_code}",
                state,
            )
            raise SystemHalt(gate.detail)

    state = ctx.state_manager.write_plan_mutation(
        state, proposed_plan, approved_diff_sha256=approved_hash
    )
    if not ctx.objective_verifier.verify(state):
        state = ctx.objective_verifier.restore_if_tampered(state)
    return state


def handle_plan_paralysis(ctx: HermesContext, state: dict[str, Any], *, detail: str) -> None:
    """T28 P5 override: revert to last_good_plan, freeze, T30."""
    import json

    import config.loop_config as loop_config

    path = loop_config.LAST_GOOD_PLAN_PATH
    if path.is_file():
        plan = json.loads(path.read_text(encoding="utf-8"))
        proposal = PlanMutateProposal(
            master_plan=plan,
            justification="T28 plan paralysis rollback to last_good_plan",
            delta_reason="SCOPE_CLARIFICATION",
        )
        guard = ctx.mutation_guard.validate_mutation(
            state,
            proposal.master_plan,
            justification=proposal.justification,
            delta_reason=proposal.delta_reason,
            repo_root=ctx.repo_root,
        )
        if guard.ok:
            state = ctx.state_manager.write_plan_mutation(
                state,
                guard.data["proposed_plan"],
                approved_diff_sha256=guard.data["proposed_diff_sha256"],
            )

    runtime = dict(state.get("runtime") or {})
    runtime["frozen"] = True
    runtime["plan_paralysis"] = True
    ctx.state_manager.write_runtime_field(state, "runtime", runtime)
    ctx.escalation.alert(f"Plan paralysis at P5: {detail}", state)
    raise SystemHalt("Plan paralysis — pipeline frozen (T28/T30)")
