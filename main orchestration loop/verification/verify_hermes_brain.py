#!/usr/bin/env python3
"""Verify Hermes brain (T26), P5 replan, T27 phase gating, T28 paralysis, contracts."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

LOOP_DIR = Path(__file__).resolve().parents[1]
HERMES_ROOT = LOOP_DIR.parent
sys.path.insert(0, str(LOOP_DIR))
sys.path.insert(0, str(HERMES_ROOT))

os.environ.setdefault("HERMES_SKIP_HERMES_BRAIN", "1")
os.environ.setdefault("HERMES_DRY_RUN", "1")

from hermes_secrets import load_local_env  # noqa: E402

load_local_env()

from models.schema_contracts.plan_mutate import PlanMutateProposal  # noqa: E402
from models.schema_contracts.tool_call import ToolCallProposal  # noqa: E402
from orchestrator.bootstrap import build_context  # noqa: E402
from orchestrator.contracts import register_all  # noqa: E402
from orchestrator.plan_brain import (  # noqa: E402
    commit_plan_proposal,
    is_identity_plan,
    merge_plan_statuses,
    propose_plan,
)
from orchestrator.tool_gate import PhaseToolGate  # noqa: E402
from orchestrator.phases.phase5_reconcile import run_phase5  # noqa: E402
from tools.common import Phase, SystemHalt  # noqa: E402
from tools.governance.t05_horizon_controller import HorizonWindowController  # noqa: E402
from tools.orchestration.t26_model_router import TaskClass  # noqa: E402
import config.loop_config as lc  # noqa: E402
from tools.governance.t04_plan_mutation_guard import PlanMutationGuard  # noqa: E402
from tools.safety.t23_state_journal import StateJournal  # noqa: E402
from tools.governance.t03_pipeline_state_manager import PipelineStateManager  # noqa: E402


def main() -> int:
    print("=== verify_hermes_brain ===")
    failures: list[str] = []

    # Schema contracts
    raw = json.dumps(
        {
            "master_plan": [{"step_id": "S001", "title": "t", "status": "pending"}],
            "justification": "test",
            "delta_reason": "SCOPE_CLARIFICATION",
        }
    )
    try:
        p = PlanMutateProposal.from_raw(raw)
        if p.delta_reason != "SCOPE_CLARIFICATION":
            failures.append("PlanMutateProposal parse failed")
        else:
            print("[OK] PlanMutateProposal schema")
    except Exception as exc:
        failures.append(f"PlanMutateProposal: {exc}")

    try:
        tc = ToolCallProposal.from_raw('{"tool_id":"T07","args":{}}')
        if tc.tool_id != "T07":
            failures.append("ToolCallProposal parse failed")
        else:
            print("[OK] ToolCallProposal schema")
    except Exception as exc:
        failures.append(f"ToolCallProposal: {exc}")

    # merge_plan_statuses preserves green
    merged = merge_plan_statuses(
        [{"step_id": "S001", "status": "green", "title": "a"}],
        [{"step_id": "S001", "title": "b", "status": "pending"}],
    )
    if merged[0]["status"] != "green":
        failures.append("merge_plan_statuses did not preserve green status")
    else:
        print("[OK] merge_plan_statuses preserves step status")

    ctx = build_context(HERMES_ROOT)
    register_all(ctx.phase_controller)

    # T27 phase gate
    gate = PhaseToolGate(ctx.tool_validator)
    try:
        gate.assert_tool("T09", Phase.P1)
        failures.append("T27 should reject T09 in P1")
    except SystemHalt:
        print("[OK] T27 rejects T09 in P1")

    try:
        gate.assert_phase_tools(Phase.P5)
        print("[OK] T27 P5 allowlist passes registry")
    except SystemHalt as exc:
        failures.append(f"T27 P5 allowlist: {exc}")

    # T05 context wipe + strip
    seed = json.loads((LOOP_DIR / "pipeline_state.test_trading.seed.json").read_text())
    guard = PlanMutationGuard(lc.GENESIS_BASELINE_PATH, lc.LAST_GOOD_PLAN_PATH)
    hz = HorizonWindowController(3, lc.HORIZON_OPEN_PATH, guard)
    wiped = hz.perform_context_wipe(seed)
    if not (wiped.get("runtime") or {}).get("context_wiped_at"):
        failures.append("perform_context_wipe missing context_wiped_at")
    else:
        print("[OK] T05 perform_context_wipe")

    stripped = hz.strip_context_for_hermes(wiped)
    if len(stripped.get("master_plan", [])) > len(seed.get("master_plan", [])):
        failures.append("strip_context_for_hermes expanded plan")
    else:
        print("[OK] T05 strip_context_for_hermes")

    # transition_p4_p2 registered
    if "P4_to_P2" not in ctx.phase_controller.contracts:
        failures.append("P4_to_P2 contract not registered")
    else:
        print("[OK] transition_p4_p2 registered")

    # P5 dry-run replan path
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        lc.PIPELINE_STATE_PATH = tmp_path / "pipeline_state.json"
        lc.WAL_PATH = tmp_path / "wal.jsonl"
        lc.GENESIS_BASELINE_PATH = tmp_path / "genesis_baseline.json"
        lc.LAST_GOOD_PLAN_PATH = tmp_path / "last_good_plan.json"
        lc.HORIZON_OPEN_PATH = tmp_path / "horizon_open.json"
        lc.STATE_DIR = tmp_path

        journal = StateJournal(lc.WAL_PATH)
        t03 = PipelineStateManager(lc.PIPELINE_STATE_PATH, journal)
        state = t03.ingest_seed(LOOP_DIR / "pipeline_state.test_trading.seed.json")
        from tools.governance.output_paths import bind_generated_output

        state = bind_generated_output(state, HERMES_ROOT)
        state = ctx.objective_verifier.lock_objective(state)
        state = ctx.mutation_guard.capture_genesis_baseline(state)
        state = ctx.budget.initialize(state)
        for step in state.get("master_plan", []):
            step["status"] = "green"
        state["master_plan"][0]["status"] = "pending"
        state = t03.write_runtime_field(
            state,
            "runtime",
            {
                "current_phase": "P4",
                "repo_path": str(HERMES_ROOT),
                "index": {"vectors_path": str(lc.VECTORS_PATH), "chunk_count": 1, "consistent": True},
            },
        )
        state = hz.select_window(state, git_ref="work@test")
        try:
            out = run_phase5(ctx, state, reason="window_exhausted")
            if not (out.get("runtime") or {}).get("post_p5_reconcile"):
                failures.append("P5 did not set post_p5_reconcile")
            elif not (out.get("horizon") or {}).get("window"):
                failures.append("P5 did not select next window")
            else:
                print("[OK] P5 reconcile dry-run path")
        except Exception as exc:
            failures.append(f"P5 reconcile: {exc}")

    # T26 route called when brain enabled (mock)
    os.environ["HERMES_SKIP_HERMES_BRAIN"] = "0"
    os.environ["HERMES_DRY_RUN"] = "0"
    with tempfile.TemporaryDirectory() as tmp2:
        tmp_path = Path(tmp2)
        lc.PIPELINE_STATE_PATH = tmp_path / "pipeline_state.json"
        lc.WAL_PATH = tmp_path / "wal.jsonl"
        journal2 = StateJournal(lc.WAL_PATH)
        t03b = PipelineStateManager(lc.PIPELINE_STATE_PATH, journal2)
        locked = t03b.ingest_seed(LOOP_DIR / "pipeline_state.test_trading.seed.json")
        locked = ctx.objective_verifier.lock_objective(locked)
        mock_router = MagicMock()
        mock_router.route_hermes.return_value = MagicMock(
            tier="hermes14b",
            result=MagicMock(
                parsed=PlanMutateProposal.from_state(
                    locked, justification="mock", delta_reason="SCOPE_CLARIFICATION"
                ),
                raw="{}",
            ),
        )
        ctx.model_router = mock_router
        proposal = propose_plan(
            ctx,
            locked,
            TaskClass.PLAN_GENERATE,
            ast_meta="test",
            reason="unit",
            strip_horizon=False,
            fallback_justification="fb",
        )
        if not mock_router.route_hermes.called:
            failures.append("propose_plan did not call T26 when brain enabled")
        elif proposal.justification != "mock":
            failures.append("propose_plan did not use T26 parsed proposal")
        else:
            print("[OK] propose_plan routes via T26")

    if failures:
        print("[FAIL]")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("[OK] Hermes brain verification complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
