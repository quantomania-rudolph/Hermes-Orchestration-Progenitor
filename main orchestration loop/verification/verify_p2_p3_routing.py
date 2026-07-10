#!/usr/bin/env python3
"""Verify P2 DEVIATION + T13→P5 and P3 PLAN_OMISSION / ancestral rollback routing."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

LOOP_DIR = Path(__file__).resolve().parents[1]
HERMES_ROOT = LOOP_DIR.parent
sys.path.insert(0, str(LOOP_DIR))
sys.path.insert(0, str(HERMES_ROOT))

from orchestrator.gauntlet import GauntletResult, run_p2_gauntlet  # noqa: E402
from orchestrator.phases.phase2_implement import (  # noqa: E402
    Phase2Result,
    _signals_deviation,
    run_phase2_step,
)
from orchestrator.phases.phase3_audit import Phase3Result, run_phase3_step  # noqa: E402
from tools.common import Phase  # noqa: E402


def _state(*, strikes: int = 0) -> dict:
    ledger = {}
    if strikes:
        ledger["generated/routing_test/a.py"] = strikes
    return {
        "core_objective": {"text": "obj", "hash": "sha256:x", "locked": True},
        "genesis_baseline": {"step_count": 2, "output_slug": "routing_test"},
        "master_plan": [
            {
                "step_id": "S000",
                "title": "base",
                "intent": "base module",
                "target_files": ["generated/routing_test/base.py"],
                "depends_on": [],
                "status": "green",
            },
            {
                "step_id": "S001",
                "title": "t",
                "intent": "i",
                "target_files": ["generated/routing_test/a.py"],
                "depends_on": ["S000"],
                "status": "implemented",
            },
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
        "strike_ledger": ledger,
        "wal": {"intent_to_integrate": None},
        "tool_registry_version": "test",
        "journal": [],
        "runtime": {"current_phase": "P2"},
    }


def _p3_ctx(strikes: int = 1) -> MagicMock:
    ctx = MagicMock()
    ctx.repo_root = HERMES_ROOT
    ctx.loop_dir = LOOP_DIR
    ctx.tool_validator = MagicMock()
    st = _state(strikes=strikes)
    ctx.state_manager.read.return_value = st
    ctx.state_manager.write_step_status.side_effect = lambda s, sid, status: {
        **s,
        "master_plan": [
            {**step, "status": status if step.get("step_id") == sid else step.get("status")}
            for step in s.get("master_plan", [])
        ],
    }
    ctx.state_manager.write_runtime_field.side_effect = lambda s, *_a, **_k: s
    ctx.test_runner.run_tests_for_step.return_value = MagicMock(
        ok=False, output="AssertionError: missing x"
    )
    ctx.test_runner.local_state_purge.return_value = None
    ctx.fuzzer.run_against_schemas.return_value = MagicMock(ok=True, crashes=[])
    ctx.error_normalizer.normalize.return_value = MagicMock(
        signature="AssertionError: missing x", hash="h1"
    )
    ctx.triage.classify.return_value = MagicMock(
        kind="CLASSIFIED", classification="PLAN_OMISSION", confidence=0.9, detail=""
    )
    ctx.strike_breaker.record_strike.return_value = (_state(strikes=strikes + 1), strikes + 1)
    ctx.strike_breaker.is_strikeout.return_value = False
    ctx.cursor_gate.run.return_value = MagicMock(status=MagicMock(value="CURSOR_UNAVAILABLE"))
    ctx.boundary_compiler.compile_step.return_value = MagicMock(boundaries={})
    ctx.git_snapshot.take_snapshot.return_value = MagicMock()
    ctx.git_snapshot.restore.return_value = None
    ctx.semantic.architecture_md = LOOP_DIR / "docs" / "architecture.md"
    return ctx


def main() -> int:
    print("=== verify_p2_p3_routing ===")
    failures: list[str] = []

    if not _signals_deviation("Reviewer says EXIT_CODE_412 shared-schema change needed"):
        failures.append("EXIT_CODE_412 marker not detected")
    if not _signals_deviation("plan remap required for schema mismatch"):
        failures.append("plan remap marker not detected")

    t13 = GauntletResult(False, "T13", "alignment fail", force_p5=True)
    if not t13.force_p5:
        failures.append("T13 gauntlet should set force_p5")

    ctx = MagicMock()
    ctx.repo_root = HERMES_ROOT
    ctx.loop_dir = LOOP_DIR
    ctx.semantic.check.return_value = MagicMock(ok=False, raw="semantic drift", items=[])
    ctx.diff_analyzer.single_step_audit.return_value = MagicMock(ok=True, violations=[])
    ctx.compiler.check_files.return_value = MagicMock(ok=True, output="")
    with patch("orchestrator.gauntlet.audit_step_outputs", return_value=MagicMock(ok=True, stray_files=[])):
        result = run_p2_gauntlet(
            ctx,
            repo_root=HERMES_ROOT,
            boundaries={},
            target_files=[],
            wrapped_prompt="w",
            code_summary="def run_pipeline(): pass",
        )
    if not result.force_p5 or result.stage != "T13":
        failures.append(f"T13 routing gauntlet expected force_p5, got {result}")

    p2_ctx = MagicMock()
    p2_ctx.repo_root = HERMES_ROOT
    p2_ctx.tool_validator = MagicMock()
    p2_ctx.state_manager.read.return_value = _state()
    p2_ctx.state_manager.write_step_status.side_effect = lambda s, *_a, **_k: s
    p2_ctx.state_manager.write_runtime_field.side_effect = lambda s, *_a, **_k: s
    p2_ctx.budget.record_usage.side_effect = lambda s, **_k: s
    p2_ctx.budget.preflight_floor_clear.return_value = True
    p2_ctx.ast_mapper.build_map.return_value = None
    p2_ctx.ast_mapper.inject_interfaces.return_value = ""
    p2_ctx.ast_mapper.meta_summary.return_value = "AST meta"
    p2_ctx.rag.run.return_value = MagicMock(ok=False)
    p2_ctx.objective_envelope.wrap.return_value = "wrap"
    p2_ctx.boundary_compiler.compile_step.return_value = MagicMock(
        boundaries={}, text=""
    )
    p2_ctx.cursor_gate.run.return_value = MagicMock(status=MagicMock(value="CURSOR_UNAVAILABLE"))
    p2_ctx.git_snapshot.take_snapshot.return_value = {}
    p2_ctx.git_snapshot.restore.return_value = None
    p2_ctx.diff_analyzer.diff_summary.return_value = "summary"
    p2_ctx.error_normalizer.normalize.return_value = MagicMock(hash="gauntlet-hash")

    with patch("orchestrator.phases.phase2_implement.is_dry_run", return_value=True):
        with patch("orchestrator.phases.phase2_implement.run_p2_gauntlet") as mock_g:
            mock_g.return_value = GauntletResult(False, "T13", "fail", force_p5=True)
            _, p2 = run_phase2_step(p2_ctx, _state(), "S001")
    if p2 != Phase2Result.DEVIATION:
        failures.append(f"T13 gauntlet fail should return DEVIATION, got {p2}")

    p3_ctx = _p3_ctx(strikes=0)
    p3_ctx.triage.classify.return_value = MagicMock(
        kind="CLASSIFIED", classification="PLAN_OMISSION", confidence=0.9, detail=""
    )
    _, p3 = run_phase3_step(p3_ctx, _state(), "S001")
    if p3 != Phase3Result.PLAN_OMISSION:
        failures.append(f"PLAN_OMISSION should defer to P5, got {p3}")

    p3_ctx2 = _p3_ctx(strikes=1)
    p3_ctx2.triage.classify.return_value = MagicMock(
        kind="CLASSIFIED", classification="CODE_BUG", confidence=0.9, detail=""
    )
    with patch("orchestrator.phases.phase3_audit.find_ancestral_defect", return_value="S000"):
        _, p3a = run_phase3_step(p3_ctx2, _state(strikes=1), "S001")
    if p3a != Phase3Result.PLAN_OMISSION:
        failures.append(f"ancestral rollback should route to P5, got {p3a}")

    if failures:
        for msg in failures:
            print(f"[FAIL] {msg}")
        return 1

    print("[OK] P2 DEVIATION + P3 omission/ancestral routing (no inline mutation)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
