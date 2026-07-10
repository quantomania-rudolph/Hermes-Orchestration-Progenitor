#!/usr/bin/env python3
"""Verify T04 topo-sort, macro-envelope, virtual provisioning."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOOP_DIR))

from tools.governance.t04_plan_mutation_guard import PlanMutationGuard  # noqa: E402


def main() -> int:
    print("=== verify_t04_mutation_guard ===")
    with tempfile.TemporaryDirectory() as tmp:
        genesis = Path(tmp) / "genesis.json"
        last_good = Path(tmp) / "last_good.json"
        guard = PlanMutationGuard(genesis, last_good)
        seed = json.loads((LOOP_DIR / "pipeline_state.seed.json").read_text(encoding="utf-8"))
        state = guard.capture_genesis_baseline(seed)

        result = guard.validate_mutation(
            state,
            state["master_plan"],
            justification="test",
            delta_reason="SCOPE_CLARIFICATION",
            repo_root=LOOP_DIR.parent,
        )
        if not result.ok:
            print(f"[FAIL] Valid plan rejected: {result.message}")
            return 1
        print("[OK] Seed plan passes guard")

        bad_plan = list(state["master_plan"]) + [
            {
                "step_id": "S999",
                "title": "Out of scope",
                "target_files": ["C:/outside/evil.py"],
                "line_bounds": [0, -1],
                "depends_on": [],
                "status": "pending",
            }
        ]
        bad = guard.validate_mutation(
            state,
            bad_plan,
            justification="test",
            delta_reason="NEW_CONSTRAINT_DISCOVERED",
            repo_root=LOOP_DIR.parent,
        )
        if bad.ok:
            print("[FAIL] Macro-envelope should reject out-of-dir file")
            return 1
        print(f"[OK] Macro-envelope blocked: {bad.message[:80]}")

        cycle_plan = [
            {"step_id": "A", "depends_on": ["B"], "target_files": ["main orchestration loop/x.py"], "status": "pending"},
            {"step_id": "B", "depends_on": ["A"], "target_files": ["main orchestration loop/y.py"], "status": "pending"},
        ]
        cycle = guard.validate_mutation(
            state,
            cycle_plan,
            justification="test",
            delta_reason="DEPENDENCY_REORDER",
            repo_root=LOOP_DIR.parent,
        )
        if cycle.ok:
            print("[FAIL] Cycle should be rejected")
            return 1
        print(f"[OK] Cycle detected: {cycle.message[:60]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
