#!/usr/bin/env python3
"""Verify all 30 tools have implementation modules on disk."""

from __future__ import annotations

import json
import sys
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parents[1]
TOOL_MAP = {
    "T01": "tools/governance/t01_objective_envelope.py",
    "T02": "tools/governance/t02_objective_hash.py",
    "T03": "tools/governance/t03_pipeline_state_manager.py",
    "T04": "tools/governance/t04_plan_mutation_guard.py",
    "T05": "tools/governance/t05_horizon_controller.py",
    "T06": "tools/context/t06_ast_mapper.py",
    "T07": "tools/context/t07_rag_provisioner.py",
    "T08": "tools/context/t08_scope_boundary_compiler.py",
    "T09": "tools/agents/t09_agent_creator.py",
    "T10": "tools/agents/t10_agent_reviewer.py",
    "T11": "tools/agents/t11_cursor_gate.py",
    "T12": "tools/verification/t12_compiler_check.py",
    "T13": "tools/verification/t13_semantic_checker.py",
    "T14": "tools/verification/t14_diff_analyzer.py",
    "T15": "tools/verification/t15_git_snapshot.py",
    "T16": "tools/verification/t16_test_runner.py",
    "T17": "tools/verification/t17_fuzzer.py",
    "T18": "tools/verification/t18_triage_classifier.py",
    "T19": "tools/verification/t19_error_normalizer.py",
    "T20": "tools/safety/t20_strike_breaker.py",
    "T21": "tools/safety/t21_budget_accountant.py",
    "T22": "tools/safety/t22_cycle_detector.py",
    "T23": "tools/safety/t23_state_journal.py",
    "T24": "tools/meta/t24_tool_synthesizer.py",
    "T25": "tools/meta/t25_tool_registry.py",
    "T26": "tools/orchestration/t26_model_router.py",
    "T27": "tools/orchestration/t27_tool_call_validator.py",
    "T28": "tools/orchestration/t28_paralysis_breaker.py",
    "T29": "tools/orchestration/t29_phase_controller.py",
    "T30": "tools/orchestration/t30_human_escalation.py",
}


def main() -> int:
    print("=== verify_all_tools_exist ===")
    reg = json.loads((LOOP_DIR / "config/static_tool_registry.json").read_text(encoding="utf-8"))
    reg_ids = {t["id"] for t in reg["tools"]}
    missing_files = []
    for tid, relpath in TOOL_MAP.items():
        if not (LOOP_DIR / relpath).is_file():
            missing_files.append(f"{tid}: {relpath}")
    if missing_files:
        print("[FAIL] Missing implementation files:")
        for m in missing_files:
            print(f"  {m}")
        return 1
    if set(TOOL_MAP) != reg_ids:
        print(f"[FAIL] Registry mismatch: {reg_ids - set(TOOL_MAP)}")
        return 1
    print(f"[OK] All {len(TOOL_MAP)} tool modules present")
    for extra in ("models/hermes.py", "agents/cursor_sdk.py", "agents/sync_barrier.py"):
        if not (LOOP_DIR / extra).is_file():
            print(f"[FAIL] Missing layer file: {extra}")
            return 1
    print("[OK] Model and agent layers present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
