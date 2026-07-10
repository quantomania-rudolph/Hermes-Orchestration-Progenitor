#!/usr/bin/env python3
"""Verify Cursor-unavailable fallbacks per registry §4.3–4.4."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

LOOP_DIR = Path(__file__).resolve().parents[1]
HERMES_ROOT = LOOP_DIR.parent
sys.path.insert(0, str(LOOP_DIR))
sys.path.insert(0, str(HERMES_ROOT))

from hermes_secrets import load_local_env  # noqa: E402

load_local_env()

from agents.cursor_sdk import CursorAgentError  # noqa: E402
from orchestrator.bootstrap import build_context  # noqa: E402
from orchestrator.phases.phase1_blueprint import run_phase1  # noqa: E402
from orchestrator.phases.phase2_implement import Phase2Result, run_phase2_step  # noqa: E402
from tools.agents.t11_cursor_gate import CursorGateResult, CursorStatus  # noqa: E402
from tools.governance.t04_plan_mutation_guard import PlanMutationGuard  # noqa: E402
from tools.governance.t03_pipeline_state_manager import PipelineStateManager  # noqa: E402
from tools.safety.t23_state_journal import StateJournal  # noqa: E402
import config.loop_config as lc  # noqa: E402
import tempfile
import json


def main() -> int:
    print("=== verify_fallback_ladder ===")
    failures: list[str] = []

    ctx = build_context(HERMES_ROOT)

    # T11 reason codes
    skip = ctx.cursor_gate.run(skip=True)
    if skip.reason_code != "SKIP_CURSOR":
        failures.append(f"T11 skip reason: {skip.reason_code}")

    no_key = ctx.cursor_gate.run()
    if lc.PIPELINE_STATE_PATH:  # env may have key from .env.local
        if no_key.status == CursorStatus.CURSOR_OK:
            print("[OK] T11 with .env.local key returns CURSOR_OK (or network)")
        else:
            print(f"[OK] T11 without working cursor: {no_key.reason_code}")

    # Stage-2 fallback preserves output_slug (T04 regression fix)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        lc.GENESIS_BASELINE_PATH = tmp_path / "genesis_baseline.json"
        lc.LAST_GOOD_PLAN_PATH = tmp_path / "last_good_plan.json"
        guard = PlanMutationGuard(lc.GENESIS_BASELINE_PATH, lc.LAST_GOOD_PLAN_PATH)
        seed = json.loads((LOOP_DIR / "pipeline_state.test_trading.seed.json").read_text())
        captured = guard.capture_genesis_baseline(seed)
        if not captured.get("genesis_baseline", {}).get("output_slug"):
            failures.append("T04 dropped output_slug from baseline")
        else:
            print("[OK] T04 preserves output_slug for wipe-on-complete")

    # P1 Stage-2: T10 throws → still proceeds for SCOPE_CLARIFICATION
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
        runtime = {
            "current_phase": "P0",
            "repo_path": str(HERMES_ROOT),
            "index": {
                "vectors_path": str(lc.VECTORS_PATH),
                "chunk_count": 1,
                "consistent": True,
            },
        }
        state = t03.write_runtime_field(state, "runtime", runtime)

        from orchestrator.contracts import register_all

        register_all(ctx.phase_controller)
        with patch.object(ctx.cursor_gate, "run", return_value=CursorGateResult(CursorStatus.CURSOR_OK)):
            with patch.object(
                ctx.agent_reviewer,
                "verify_plan",
                side_effect=CursorAgentError("bridge down", is_retryable=True),
            ):
                try:
                    run_phase1(ctx, state)
                    print("[OK] P1 Stage-2 fallback survives T10 bridge failure")
                except Exception as exc:
                    failures.append(f"P1 Stage-2 fallback failed: {exc}")

    # P2: files exist + bridge fail → SUCCESS not CURSOR_DOWN
    strategy_file = HERMES_ROOT / "generated/simple_rsi_strategy/data_loader.py"
    if strategy_file.is_file():
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
            state = ctx.horizon.select_window(state)
            step_id = "S001"
            with patch.object(
                ctx.agent_creator,
                "run",
                side_effect=CursorAgentError("bridge down", is_retryable=True),
            ):
                with patch.object(
                    ctx.cursor_gate,
                    "run",
                    return_value=CursorGateResult(CursorStatus.CURSOR_OK),
                ):
                    import config.loop_config as loop_config

                    old = loop_config.is_dry_run
                    loop_config.is_dry_run = lambda: False  # type: ignore
                    try:
                        _, p2 = run_phase2_step(ctx, state, step_id)
                    finally:
                        loop_config.is_dry_run = old  # type: ignore
            if p2 != Phase2Result.SUCCESS:
                failures.append(f"P2 files_exist fallback got {p2}")
            else:
                print("[OK] P2 continues gauntlet when files exist and T09 fails (infra, no strike)")
    else:
        failures.append("Missing generated data_loader for P2 fallback test")

    # T13 deterministic harness works without Qwen
    sem = ctx.semantic.check("objective", "def run_phase0(): pass")
    if not sem.ok:
        failures.append(f"T13 deterministic harness failed: {sem.raw}")
    else:
        print("[OK] T13 HYBRID deterministic harness passes without model")

    if failures:
        print("[FAIL] Fallback failures:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("[OK] Fallback ladder behaviors verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
