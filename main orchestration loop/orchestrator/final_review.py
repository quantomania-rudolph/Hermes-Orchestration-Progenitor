"""§17 final robustness review before PROJECT COMPLETE."""

from __future__ import annotations

import os
import re
from typing import Any

from orchestrator.bootstrap import HermesContext
from tools.governance.output_hygiene import audit_step_outputs


def _audit_objective_clauses(state: dict[str, Any]) -> list[str]:
    objective = (state.get("core_objective") or {}).get("text", "")
    if not objective.strip():
        return ["core_objective text is empty"]
    stop = {
        "build",
        "the",
        "with",
        "from",
        "that",
        "this",
        "and",
        "for",
        "into",
        "driven",
    }
    keywords = [
        w.lower()
        for w in re.findall(r"[A-Za-z]{5,}", objective)
        if w.lower() not in stop
    ][:16]
    if not keywords:
        return []
    plan_text = " ".join(
        f"{s.get('title', '')} {s.get('intent', '')}"
        for s in state.get("master_plan", [])
    ).lower()
    hits = sum(1 for k in keywords if k in plan_text)
    if hits < max(2, len(keywords) // 5):
        return [f"objective keywords sparsely reflected in plan ({hits}/{len(keywords)} hits)"]
    return []


def _audit_journal(state: dict[str, Any]) -> list[str]:
    journal = state.get("journal") or []
    if not journal:
        return ["journal is empty — run not resumable"]
    last = journal[-1]
    if not last.get("transition_type"):
        return ["journal last entry missing transition_type"]
    return []


def _audit_synthesized_tools(ctx: HermesContext) -> list[str]:
    sys_tools = ctx.repo_root / "system_tools"
    if not sys_tools.is_dir():
        return []
    failures: list[str] = []
    for path in sys_tools.glob("*.py"):
        if path.name.startswith("_"):
            continue
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as exc:
            failures.append(f"synthesized tool syntax error {path.name}: {exc}")
    return failures


def run_final_robustness_review(ctx: HermesContext, state: dict[str, Any]) -> tuple[bool, list[str]]:
    """Return (ok, failure_messages). Does not mutate repo or pipeline state."""
    failures: list[str] = []
    plan = state.get("master_plan") or []

    if not plan:
        failures.append("master_plan is empty")
    elif not all(s.get("status") == "green" for s in plan):
        pending = [s.get("step_id") for s in plan if s.get("status") != "green"]
        failures.append(f"steps not green: {pending}")

    blocked = [s.get("step_id") for s in plan if s.get("status") in ("blocked", "contested")]
    if blocked:
        failures.append(f"blocked/contested steps remain: {blocked}")

    if (state.get("wal") or {}).get("intent_to_integrate"):
        failures.append("dangling WAL intent_to_integrate")

    if state.get("strike_ledger"):
        failures.append(f"strike_ledger not empty: {list(state['strike_ledger'].keys())[:5]}")

    if not ctx.objective_verifier.verify(state):
        failures.append("core_objective hash mismatch (T02)")

    failures.extend(_audit_objective_clauses(state))

    runtime = state.get("runtime") or {}
    if runtime.get("frozen"):
        failures.append("pipeline still frozen")

    slug = (
        runtime.get("output_slug")
        or (state.get("genesis_baseline") or {}).get("output_slug")
        or os.environ.get("HERMES_OUTPUT_SLUG", "").strip()
    )
    if slug:
        targets: list[str] = []
        for step in plan:
            targets.extend(step.get("target_files") or [])
        if targets:
            hygiene = audit_step_outputs(ctx.repo_root, targets)
            if not hygiene.ok:
                failures.append(
                    "output hygiene: unauthorized scratch files: "
                    + ", ".join(hygiene.stray_files[:8])
                )

    macro = ctx.diff_analyzer.cumulative_macro_audit(ctx.repo_root, state)
    if not macro.ok:
        failures.append(
            "cumulative T14 macro-diff: " + "; ".join(macro.violations[:5])
        )

    if not ctx.budget.within_cap(state):
        failures.append("budget cap exceeded (T21)")

    failures.extend(_audit_journal(state))
    failures.extend(_audit_synthesized_tools(ctx))

    skip_runtime = os.environ.get("HERMES_SKIP_FINAL_TESTS", "0").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if not skip_runtime:
        test = ctx.test_runner.run_tests(ctx.repo_root)
        if not test.ok:
            failures.append(f"final pytest suite failed: {(test.output or '')[:400]}")
        fuzz = ctx.fuzzer.run_against_schemas(ctx.loop_dir / "docs" / "schemas")
        if not fuzz.ok and fuzz.crashes:
            failures.append(f"final fuzz failures: {fuzz.crashes[:3]}")

    return len(failures) == 0, failures
