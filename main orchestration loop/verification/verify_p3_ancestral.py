#!/usr/bin/env python3
"""Verify P3 ancestral-defect detection (blueprint §10)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

LOOP_DIR = Path(__file__).resolve().parents[1]
HERMES_ROOT = LOOP_DIR.parent
sys.path.insert(0, str(LOOP_DIR))
sys.path.insert(0, str(HERMES_ROOT))

from orchestrator.p3_ancestral import find_ancestral_defect  # noqa: E402
from tools.verification.t16_test_runner import TestResult  # noqa: E402


def _state() -> dict:
    return {
        "master_plan": [
            {
                "step_id": "S000",
                "target_files": ["generated/anc_test/base.py"],
                "depends_on": [],
                "status": "green",
            },
            {
                "step_id": "S001",
                "target_files": ["generated/anc_test/a.py"],
                "depends_on": ["S000"],
                "status": "implemented",
            },
        ]
    }


def main() -> int:
    print("=== verify_p3_ancestral ===")
    failures: list[str] = []

    ctx = MagicMock()
    ctx.repo_root = HERMES_ROOT
    ctx.test_runner.build_step_test_command.return_value = "python -m pytest -q"
    ctx.test_runner.run_tests.return_value = TestResult(ok=False, exit_code=1, output="fail")

    found = find_ancestral_defect(ctx, _state(), step_id="S001")
    if found != "S000":
        failures.append(f"expected ancestral S000, got {found}")

    ctx.test_runner.run_tests.return_value = TestResult(ok=True, exit_code=0, output="")
    none = find_ancestral_defect(ctx, _state(), step_id="S001")
    if none is not None:
        failures.append(f"expected no ancestral defect when tests pass, got {none}")

    if failures:
        for msg in failures:
            print(f"[FAIL] {msg}")
        return 1

    print("[OK] P3 ancestral defect detection")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
