#!/usr/bin/env python3
"""Verify T29 phase-transition pairing used by session.py (no dirty-contract leaks)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

LOOP_DIR = Path(__file__).resolve().parents[1]
HERMES_ROOT = LOOP_DIR.parent
sys.path.insert(0, str(LOOP_DIR))
sys.path.insert(0, str(HERMES_ROOT))

from orchestrator.contracts import register_all  # noqa: E402
from orchestrator.invariants import ensure_invariants  # noqa: E402
from orchestrator.session import _complete_project, _reconcile_via_p5  # noqa: E402
from tools.common import Phase  # noqa: E402
from tools.orchestration.t29_phase_controller import PhaseTransitionController  # noqa: E402


def _minimal_state(*, current_phase: str = "P4", all_green: bool = False) -> dict:
    return {
        "core_objective": {"text": "test", "hash": "sha256:x", "locked": True},
        "genesis_baseline": {"step_count": 1, "output_slug": "t29_test"},
        "master_plan": [
            {
                "step_id": "S001",
                "title": "t",
                "intent": "i",
                "target_files": [],
                "status": "green" if all_green else "pending",
            }
        ],
        "horizon": {"window": ["S001"], "cursor": "S001"},
        "budget": {
            "tokens_used": 0,
            "token_cap": 2000000,
            "usd_used": 0.0,
            "usd_cap": 5.0,
            "floor_tokens": 100000,
            "floor_usd": 0.5,
        },
        "snapshots": {},
        "strike_ledger": {},
        "wal": {"intent_to_integrate": None},
        "tool_registry_version": "test",
        "journal": [],
        "runtime": {"current_phase": current_phase},
    }


def main() -> int:
    print("=== verify_t29_session_contracts ===")
    failures: list[str] = []

    controller = PhaseTransitionController()
    register_all(controller)

    controller.transition(_minimal_state(), Phase.P4, Phase.P5)
    if not controller.has_dirty_contract():
        failures.append("transition(P4,P5) should set dirty flag")
    p45_state = _minimal_state(current_phase="P5")
    p45_state["runtime"]["post_p5_reconcile"] = True
    controller.assert_exit(p45_state, Phase.P4, Phase.P5)
    if controller.has_dirty_contract():
        failures.append("assert_exit(P4,P5) should clear dirty flag")

    controller.transition(_minimal_state(), Phase.P1, Phase.P2)
    controller.abort_pending()
    if controller.has_dirty_contract():
        failures.append("abort_pending should clear dirty flag")

    # _reconcile_via_p5 must leave controller clean and pass ensure_invariants
    def _p5_out() -> dict:
        s = _minimal_state(current_phase="P5")
        s["runtime"]["post_p5_reconcile"] = True
        return s

    phase5 = MagicMock(side_effect=lambda *a, **k: _p5_out())
    ctx = MagicMock()
    ctx.phase_controller = PhaseTransitionController()
    register_all(ctx.phase_controller)
    ctx.objective_verifier.verify.return_value = True
    ctx.budget.within_cap.return_value = True
    ctx.horizon.window_size = 3

    import orchestrator.session as session_mod

    original = session_mod.run_phase5
    session_mod.run_phase5 = phase5
    try:
        state = _minimal_state(current_phase="P4")
        ctx.phase_controller.transition(state, Phase.P1, Phase.P2)
        out = _reconcile_via_p5(
            ctx, state, reason="omission", close_from=Phase.P2, close_to=Phase.P3
        )
        if ctx.phase_controller.has_dirty_contract():
            failures.append("_reconcile_via_p5 left dirty contract after omission path")
        ensure_invariants(ctx, out)
        if phase5.call_count != 1:
            failures.append("run_phase5 not invoked once in reconcile helper")
    except Exception as exc:
        failures.append(f"_reconcile_via_p5 smoke: {exc}")
    finally:
        session_mod.run_phase5 = original

    controller.transition(_minimal_state(all_green=True, current_phase="P5"), Phase.P5, Phase.DONE)
    done_state = _minimal_state(all_green=True, current_phase="P5")
    done_state["runtime"]["current_phase"] = Phase.DONE.value
    try:
        controller.assert_exit(done_state, Phase.P5, Phase.DONE)
    except Exception as exc:
        failures.append(f"P5->DONE assert_exit failed: {exc}")

    bad_done = _minimal_state(all_green=False, current_phase="P5")
    try:
        controller.transition(bad_done, Phase.P5, Phase.DONE)
        failures.append("P5->DONE should reject non-green plan at entry")
    except Exception:
        pass

    complete_ctx = MagicMock()
    complete_ctx.phase_controller = PhaseTransitionController()
    register_all(complete_ctx.phase_controller)
    complete_ctx.horizon.project_complete.return_value = True
    complete_ctx.objective_verifier.verify.return_value = True
    complete_ctx.budget.within_cap.return_value = True
    complete_ctx.test_runner.run_tests.return_value = MagicMock(ok=True, output="")
    complete_ctx.fuzzer.run_against_schemas.return_value = MagicMock(ok=True, crashes=[])
    complete_ctx.loop_dir = LOOP_DIR
    complete_ctx.repo_root = HERMES_ROOT
    complete_ctx.state_manager.write_runtime_field.side_effect = (
        lambda s, _field, value: {**s, "runtime": value}
    )
    with patch("orchestrator.session.finalize_completed_session"):
        with patch("orchestrator.session.run_final_robustness_review", return_value=(True, [])):
            out, rc = _complete_project(complete_ctx, _minimal_state(all_green=True, current_phase="P5"))
    if rc != 0:
        failures.append(f"_complete_project expected rc=0, got {rc}")
    if complete_ctx.phase_controller.has_dirty_contract():
        failures.append("_complete_project left dirty P5->DONE contract")

    if failures:
        for msg in failures:
            print(f"[FAIL] {msg}")
        return 1

    print("[OK] T29 session contract pairing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
