#!/usr/bin/env python3
"""End-to-end trading seed dry-run with generated/ output binding."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parents[1]
HERMES_ROOT = LOOP_DIR.parent
sys.path.insert(0, str(LOOP_DIR))
sys.path.insert(0, str(HERMES_ROOT))

os.environ["HERMES_DRY_RUN"] = "1"
os.environ["HERMES_SKIP_CURSOR"] = "1"
os.environ["HERMES_WORKSPACE_ROOTS"] = str(HERMES_ROOT)


def main() -> int:
    print("=== verify_trading_pipeline ===")
    strategy = HERMES_ROOT / "generated" / "simple_rsi_strategy"
    if not strategy.is_dir():
        print("[FAIL] generated/simple_rsi_strategy missing")
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        import config.loop_config as loop_config

        loop_config.PIPELINE_STATE_PATH = tmp_path / "pipeline_state.json"
        loop_config.WAL_PATH = tmp_path / "wal.jsonl"
        loop_config.GENESIS_BASELINE_PATH = tmp_path / "genesis_baseline.json"
        loop_config.LAST_GOOD_PLAN_PATH = tmp_path / "last_good_plan.json"
        loop_config.HORIZON_OPEN_PATH = tmp_path / "horizon_open.json"
        loop_config.STATE_DIR = tmp_path

        from orchestrator.session import run_master_session

        seed = LOOP_DIR / "pipeline_state.test_trading.seed.json"
        rc = run_master_session(seed_path=seed, repo_path=HERMES_ROOT, resume=False)
        if rc != 0:
            print(f"[FAIL] Trading session returned {rc}")
            return 1

        state = json.loads(loop_config.PIPELINE_STATE_PATH.read_text(encoding="utf-8"))
        for step in state.get("master_plan", []):
            if step.get("status") != "green":
                print(f"[FAIL] {step['step_id']} status={step.get('status')}")
                return 1
            for tf in step.get("target_files", []):
                if not tf.startswith("generated/simple_rsi_strategy/"):
                    print(f"[FAIL] target not under generated/: {tf}")
                    return 1
                if not (HERMES_ROOT / tf).is_file():
                    print(f"[FAIL] missing on disk: {tf}")
                    return 1

        runtime = state.get("runtime") or {}
        if runtime.get("output_slug") != "simple_rsi_strategy":
            print(f"[FAIL] output_slug={runtime.get('output_slug')}")
            return 1

        pnl = strategy / "reports" / "pnl_report.json"
        if not pnl.is_file():
            print("[FAIL] pnl_report.json missing")
            return 1

        print(f"[OK] All {len(state['master_plan'])} trading steps green under generated/")
        print(f"[OK] PNL report present: {pnl}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
