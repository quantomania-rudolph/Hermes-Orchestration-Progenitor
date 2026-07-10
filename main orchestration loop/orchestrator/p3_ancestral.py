"""P3 ancestral-defect detection (blueprint §10)."""

from __future__ import annotations

from orchestrator.bootstrap import HermesContext


def find_ancestral_defect(
    ctx: HermesContext,
    state: dict,
    *,
    step_id: str,
) -> str | None:
    """
    After repeated CODE_BUG on step_id, check whether a green ancestor's outputs
    cause the failure. Returns ancestor step_id to contest, or None.
    """
    plan = {s.get("step_id"): s for s in state.get("master_plan", [])}
    step = plan.get(step_id)
    if not step:
        return None

    visited: set[str] = set()
    queue = list(step.get("depends_on") or [])
    while queue:
        aid = queue.pop(0)
        if aid in visited or aid not in plan:
            continue
        visited.add(aid)
        ancestor = plan[aid]
        if ancestor.get("status") != "green":
            queue.extend(ancestor.get("depends_on") or [])
            continue

        targets = list(ancestor.get("target_files") or [])
        if not targets:
            continue
        cmd = ctx.test_runner.build_step_test_command(ctx.repo_root, ancestor)
        if not cmd:
            continue
        result = ctx.test_runner.run_tests(ctx.repo_root, command=cmd)
        if not result.ok:
            print(f"[P3] Ancestral defect: {aid} green but tests fail - contesting ancestor")
            return aid
        queue.extend(ancestor.get("depends_on") or [])
    return None
