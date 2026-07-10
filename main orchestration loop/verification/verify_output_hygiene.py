#!/usr/bin/env python3
"""Verify output hygiene guard and clean vault_lr_strategy scratch files."""

from __future__ import annotations

import sys
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parents[1]
HERMES_ROOT = LOOP_DIR.parent
sys.path.insert(0, str(LOOP_DIR))

from tools.governance.output_hygiene import audit_step_outputs  # noqa: E402


def main() -> int:
    print("=== verify_output_hygiene ===")
    targets = [
        "generated/vault_lr_strategy/data_loader.py",
        "generated/vault_lr_strategy/sample_data/aapl_5min_sample.csv",
        "generated/vault_lr_strategy/signal_model.py",
        "generated/vault_lr_strategy/backtest_pnl.py",
        "generated/vault_lr_strategy/tests/test_backtest_pnl.py",
        "generated/vault_lr_strategy/reports/pnl_report.json",
        "generated/vault_lr_strategy/reports/pnl_report.md",
    ]
    result = audit_step_outputs(HERMES_ROOT, targets)
    if result.stray_files:
        print(f"[INFO] stray files detected: {result.stray_files}")
        for rel in result.stray_files:
            path = HERMES_ROOT / rel
            if path.is_file():
                path.unlink()
                print(f"[OK] removed {rel}")
        result = audit_step_outputs(HERMES_ROOT, targets)
    if not result.ok:
        print(f"[FAIL] stray remains: {result.stray_files}")
        return 1
    print("[OK] generated/vault_lr_strategy has no unauthorized scratch files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
