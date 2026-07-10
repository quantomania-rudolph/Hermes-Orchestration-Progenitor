#!/usr/bin/env python3
"""Verify T23 COMPLETE_INTEGRATION recovery wiring."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parents[1]
HERMES_ROOT = LOOP_DIR.parent
sys.path.insert(0, str(LOOP_DIR))
sys.path.insert(0, str(HERMES_ROOT))

from tools.safety.t23_state_journal import RecoveryAction, StateJournal  # noqa: E402


def main() -> int:
    print("=== verify_t23_recovery ===")
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        wal = Path(tmpdir) / "wal.jsonl"
        journal = StateJournal(wal)
        state = {
            "wal": {"intent_to_integrate": "S002"},
            "runtime": {},
            "journal": [],
        }
        action = journal.detect_interrupted_run(state)
        if action != RecoveryAction.COMPLETE_INTEGRATION:
            failures.append(f"expected COMPLETE_INTEGRATION, got {action}")

        recovered = journal.execute_recovery(action, state)
        runtime = recovered.get("runtime") or {}
        if runtime.get("recovery_action") != RecoveryAction.COMPLETE_INTEGRATION.value:
            failures.append("execute_recovery missing recovery_action runtime flag")
        if runtime.get("recovery_step_id") != "S002":
            failures.append(f"expected recovery_step_id S002, got {runtime.get('recovery_step_id')}")

    if failures:
        for msg in failures:
            print(f"[FAIL] {msg}")
        return 1

    print("[OK] T23 COMPLETE_INTEGRATION recovery")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
