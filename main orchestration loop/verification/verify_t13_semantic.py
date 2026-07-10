#!/usr/bin/env python3
"""Verify T13 semantic checker domain-aware rubric."""

from __future__ import annotations

import sys
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOOP_DIR))

from tools.verification.t13_semantic_checker import SemanticChecker  # noqa: E402


def main() -> int:
    print("=== verify_t13_semantic ===")
    failures: list[str] = []
    checker = SemanticChecker(LOOP_DIR / "docs" / "architecture.md")

    orch = checker.check(
        "wrap",
        "def run_phase0(ctx): ctx.state_manager.write_runtime_field(state, 'x', {})",
        target_files=["main orchestration loop/orchestrator/phases/phase0_genesis.py"],
    )
    if not orch.ok:
        failures.append(f"orchestrator code should pass T13: {orch.raw}")

    bad = checker.check(
        "wrap",
        'open("pipeline_state.json", "w").write(json.dumps(state))',
        target_files=["generated/evil/hack.py"],
    )
    if bad.ok:
        failures.append("direct pipeline_state write in generated/ should fail T13")

    if failures:
        for msg in failures:
            print(f"[FAIL] {msg}")
        return 1
    print("[OK] T13 domain-aware semantic checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
