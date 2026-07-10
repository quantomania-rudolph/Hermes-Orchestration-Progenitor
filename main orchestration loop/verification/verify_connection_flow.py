#!/usr/bin/env python3
"""
End-to-end connection test: P0→P1→P2→P3→P4 with index bridge.
Runs in isolated temp state to avoid polluting production pipeline_state.json.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parents[1]
HERMES_ROOT = LOOP_DIR.parent
sys.path.insert(0, str(LOOP_DIR))
os.environ["HERMES_DRY_RUN"] = "1"
os.environ["HERMES_SKIP_CURSOR"] = "1"
os.environ["HERMES_WORKSPACE_ROOTS"] = str(HERMES_ROOT)


def main() -> int:
    print("=== verify_connection_flow ===")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        import config.loop_config as loop_config  # noqa: E402

        # Redirect state paths into temp (before orchestrator imports)
        loop_config.PIPELINE_STATE_PATH = tmp_path / "pipeline_state.json"
        loop_config.WAL_PATH = tmp_path / "wal.jsonl"
        loop_config.GENESIS_BASELINE_PATH = tmp_path / "genesis_baseline.json"
        loop_config.LAST_GOOD_PLAN_PATH = tmp_path / "last_good_plan.json"
        loop_config.HORIZON_OPEN_PATH = tmp_path / "horizon_open.json"
        loop_config.INDEX_CONSISTENCY_LOG = tmp_path / "index_consistency.jsonl"
        loop_config.STATE_DIR = tmp_path

        from orchestrator.session import run_master_session  # noqa: E402

        seed = LOOP_DIR / "pipeline_state.seed.json"
        rc = run_master_session(
            seed_path=seed,
            repo_path=HERMES_ROOT,
            resume=False,
        )
        if rc != 0:
            print(f"[FAIL] Session returned {rc}")
            return 1

        state = json.loads(loop_config.PIPELINE_STATE_PATH.read_text(encoding="utf-8"))
        steps = state.get("master_plan", [])
        greens = [s for s in steps if s.get("status") == "green"]
        if len(greens) != len(steps):
            print(f"[FAIL] Not all steps green: {[(s['step_id'], s['status']) for s in steps]}")
            return 1
        print(f"[OK] All {len(greens)} steps green")

        index = (state.get("runtime") or {}).get("index") or {}
        if not index.get("vectors_path"):
            print("[FAIL] runtime.index.vectors_path not set")
            return 1
        print(f"[OK] Index linked: {index.get('vectors_path')}")

        if index.get("consistent") is False:
            print("[WARN] Index marked inconsistent at end — may need reindex")
        else:
            print("[OK] Index consistency flag OK")

        journal = state.get("journal") or []
        phases = {e.get("transition_type") for e in journal}
        for expected in ("P0_COMPLETE", "PLAN_MUTATION", "GREEN_COMMIT"):
            if expected not in phases:
                print(f"[FAIL] Missing journal transition {expected}")
                return 1
        print(f"[OK] Journal contains {len(journal)} transitions")

    print("[OK] Full connection flow verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
