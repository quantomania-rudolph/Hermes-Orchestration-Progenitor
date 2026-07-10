#!/usr/bin/env python3
"""Run the full verification suite for the main orchestration loop."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

VERIFICATION_DIR = Path(__file__).resolve().parent

SCRIPTS = [
    "verify_all_tools_exist.py",
    "verify_tool_registry.py",
    "verify_phase_tool_matrix.py",
    "verify_tool_smoke.py",
    "verify_t03_state_manager.py",
    "verify_t04_mutation_guard.py",
    "verify_t19_normalizer.py",
    "verify_t20_strike_breaker.py",
    "verify_index_bridge.py",
    "verify_rag_quality.py",
    "verify_t09_qwen_delegate.py",
    "verify_fallback_ladder.py",
    "verify_greenlight_process.py",
    "verify_cursor_sdk.py",
    "verify_connection_flow.py",
    "verify_trading_pipeline.py",
]


def main() -> int:
    print("=" * 60)
    print("HERMES Main Loop — Full Verification Suite")
    print("=" * 60)
    failures = 0
    for name in SCRIPTS:
        path = VERIFICATION_DIR / name
        print(f"\n>>> {name}")
        extra = ["--skip-query"] if name == "verify_index_bridge.py" else []
        proc = subprocess.run(
            [sys.executable, str(path), *extra],
            cwd=str(VERIFICATION_DIR.parent.parent),
        )
        if proc.returncode != 0:
            failures += 1
            print(f"[SUITE FAIL] {name}")
        else:
            print(f"[SUITE OK] {name}")

    print("\n" + "=" * 60)
    if failures:
        print(f"FAILED: {failures}/{len(SCRIPTS)} verification scripts")
        return 1
    print(f"PASSED: all {len(SCRIPTS)} verification scripts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
