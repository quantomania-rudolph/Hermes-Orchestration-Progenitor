#!/usr/bin/env python3
"""Verify P2 gauntlet (T14→T12→T13) and P3→P4 green path on generated strategy."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parents[1]
HERMES_ROOT = LOOP_DIR.parent
sys.path.insert(0, str(LOOP_DIR))
sys.path.insert(0, str(HERMES_ROOT))

from hermes_secrets import load_local_env  # noqa: E402

load_local_env()

from orchestrator.bootstrap import build_context  # noqa: E402
from orchestrator.gauntlet import run_p2_gauntlet  # noqa: E402
from orchestrator.phases.phase3_audit import Phase3Result, run_phase3_step  # noqa: E402
from orchestrator.phases.phase4_integrate import Phase4Result, run_phase4_step  # noqa: E402
from tools.governance.output_paths import bind_generated_output  # noqa: E402


def _build_state(ctx, tmp: Path) -> dict:
    import config.loop_config as lc

    lc.PIPELINE_STATE_PATH = tmp / "pipeline_state.json"
    lc.WAL_PATH = tmp / "wal.jsonl"
    lc.GENESIS_BASELINE_PATH = tmp / "genesis_baseline.json"
    lc.LAST_GOOD_PLAN_PATH = tmp / "last_good_plan.json"
    lc.HORIZON_OPEN_PATH = tmp / "horizon_open.json"
    lc.STATE_DIR = tmp

    seed = LOOP_DIR / "pipeline_state.test_trading.seed.json"
    state = ctx.state_manager.ingest_seed(seed)
    state = bind_generated_output(state, HERMES_ROOT)
    state = ctx.objective_verifier.lock_objective(state)
    state = ctx.mutation_guard.capture_genesis_baseline(state)
    state = ctx.horizon.select_window(state)
    return state


def main() -> int:
    print("=== verify_greenlight_process ===")
    strategy = HERMES_ROOT / "generated" / "simple_rsi_strategy"
    if not strategy.is_dir():
        print("[FAIL] generated/simple_rsi_strategy missing — run trading test first")
        return 1

    ctx = build_context(HERMES_ROOT)
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        state = _build_state(ctx, tmp)
        step = state["master_plan"][2]  # S003 backtest
        step_id = step["step_id"]
        auth = ctx.boundary_compiler.compile_step(step, HERMES_ROOT)
        targets = step["target_files"]
        wrapped = ctx.objective_envelope.wrap(state, step.get("intent", ""), "")
        summary = ctx.diff_analyzer.diff_summary(HERMES_ROOT, targets)

        gauntlet = run_p2_gauntlet(
            ctx,
            repo_root=HERMES_ROOT,
            boundaries=auth.boundaries,
            target_files=targets,
            wrapped_prompt=wrapped,
            code_summary=summary,
        )
        if not gauntlet.ok:
            failures.append(f"P2 gauntlet failed at {gauntlet.stage}: {gauntlet.detail}")
        else:
            print(f"[OK] P2 gauntlet clear ({gauntlet.stage})")

        state = ctx.state_manager.write_step_status(state, step_id, "implemented")
        os.environ["HERMES_IN_SESSION"] = "1"
        state, p3 = run_phase3_step(ctx, state, step_id)
        if p3 != Phase3Result.GREEN:
            failures.append(f"P3 not green: {p3}")
        else:
            print("[OK] P3 audit green (T16/T17)")

        state, p4 = run_phase4_step(ctx, state, step_id)
        if p4 != Phase4Result.GREEN:
            failures.append(f"P4 not green: {p4}")
        else:
            print("[OK] P4 integration green (T03 GREEN_COMMIT)")

        final = ctx.state_manager.read()
        for s in final.get("master_plan", []):
            if s.get("step_id") == step_id and s.get("status") != "green":
                failures.append(f"Step {step_id} status={s.get('status')}, expected green")

        wal = final.get("wal") or {}
        if wal.get("intent_to_integrate"):
            failures.append("WAL intent_to_integrate not cleared after P4")

    if failures:
        print("[FAIL] Greenlight failures:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("[OK] Full greenlight path verified on generated strategy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
