"""
Master control loop — 02_HERMES_Semantic_Pipeline §15.
"""

from __future__ import annotations

from pathlib import Path

import config.loop_config as loop_config
from orchestrator.bootstrap import HermesContext, build_context
from orchestrator.contracts import register_all
from orchestrator.invariants import ensure_invariants
from orchestrator.phases.phase0_genesis import run_phase0
from orchestrator.phases.phase1_blueprint import run_phase1
from orchestrator.phases.phase2_implement import Phase2Result, run_phase2_step
from orchestrator.phases.phase3_audit import Phase3Result, run_phase3_step
from orchestrator.phases.phase4_integrate import Phase4Result, run_phase4_step
from orchestrator.phases.phase5_reconcile import run_phase5
from tools.common import SystemHalt
from tools.governance.output_paths import finalize_completed_session


def run_master_session(
    *,
    seed_path: Path,
    repo_path: Path,
    resume: bool = False,
) -> int:
    import os

    os.environ["HERMES_IN_SESSION"] = "1"
    ctx = build_context(repo_path)
    register_all(ctx.phase_controller)

    if resume and loop_config.PIPELINE_STATE_PATH.is_file():
        print("[session] Resuming from existing pipeline_state.json")
        state = ctx.state_manager.read()
    else:
        state = run_phase0(ctx, seed_path=seed_path, repo_path=repo_path)

    ensure_invariants(ctx, state)
    state = run_phase1(ctx, state)
    ensure_invariants(ctx, state)

    max_windows = 10
    for _ in range(max_windows):
        window = list((state.get("horizon") or {}).get("window") or [])
        if not window:
            print("[session] Horizon window empty - entering P5")
            state = run_phase5(ctx, state, reason="window_exhausted")
            if (state.get("runtime") or {}).get("current_phase") == "DONE":
                finalize_completed_session(ctx, state)
                print("[session] PROJECT COMPLETE")
                return 0
            ensure_invariants(ctx, state)
            state = run_phase1(ctx, state)
            ensure_invariants(ctx, state)
            continue

        for step_id in list(window):
            ensure_invariants(ctx, state)

            state, p2 = run_phase2_step(ctx, state, step_id)
            if p2 == Phase2Result.CURSOR_DOWN:
                ctx.escalation.alert("Cursor unavailable in P2", state)
                return 1
            if p2 == Phase2Result.DEVIATION:
                state = run_phase5(ctx, state, reason="deviation")
                break

            ensure_invariants(ctx, state)
            state, p3 = run_phase3_step(ctx, state, step_id)
            if p3 == Phase3Result.PLAN_OMISSION:
                state = run_phase5(ctx, state, reason="omission")
                break
            if p3 == Phase3Result.BLOCKED:
                ctx.escalation.alert("P3 blocked (strikes/triage)", state)
                return 1

            ensure_invariants(ctx, state)
            state, p4 = run_phase4_step(ctx, state, step_id)
            if p4 == Phase4Result.BRANCH_DRIFT:
                state = run_phase5(ctx, state, reason="drift")
                break

            ensure_invariants(ctx, state)

        if ctx.horizon.project_complete(state):
            state = run_phase5(ctx, state, reason="project_complete")
            finalize_completed_session(ctx, state)
            print("[session] PROJECT COMPLETE")
            return 0

        state = run_phase5(ctx, state, reason="window_exhausted")
        if (state.get("runtime") or {}).get("current_phase") == "DONE":
            finalize_completed_session(ctx, state)
            print("[session] PROJECT COMPLETE")
            return 0
        ensure_invariants(ctx, state)
        state = run_phase1(ctx, state)

    ctx.escalation.alert("Max window iterations", state)
    return 2


def main_entry(seed: Path, repo: Path, *, resume: bool = False) -> int:
    print("=" * 60)
    print("HERMES Main Orchestration Loop")
    print(f"  mode: {'DRY_RUN' if loop_config.is_dry_run() else 'LIVE'}")
    print(f"  seed: {seed}")
    print(f"  repo: {repo}")
    print("=" * 60)
    try:
        return run_master_session(seed_path=seed, repo_path=repo, resume=resume)
    except SystemHalt as exc:
        print(f"[HALT] {exc}")
        return 1
