#!/usr/bin/env python3
"""Verify T03 atomic writes, schema validation, hash-bound plan mutations."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOOP_DIR))

from tools.common import sha256_json, ToolError  # noqa: E402
from tools.governance.t03_pipeline_state_manager import PipelineStateManager  # noqa: E402
from tools.safety.t23_state_journal import StateJournal  # noqa: E402


def main() -> int:
    print("=== verify_t03_state_manager ===")
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "pipeline_state.json"
        wal_path = Path(tmp) / "wal.jsonl"
        seed = LOOP_DIR / "pipeline_state.seed.json"
        journal = StateJournal(wal_path)
        t03 = PipelineStateManager(state_path, journal)

        state = t03.ingest_seed(seed)
        print("[OK] Seed ingested")

        try:
            t03.write_runtime_field(state, "core_objective", {})
            print("[FAIL] Should reject non-runtime field write")
            return 1
        except ToolError:
            print("[OK] Rejected illegal field write")

        new_plan = list(state.get("master_plan", []))
        diff_hash = sha256_json({"from": state.get("master_plan", []), "to": new_plan})
        state = t03.write_plan_mutation(state, new_plan, approved_diff_sha256=diff_hash)
        print("[OK] Hash-bound plan mutation")

        try:
            t03.write_plan_mutation(state, new_plan, approved_diff_sha256="sha256:bad")
            print("[FAIL] Should reject hash mismatch")
            return 1
        except ToolError:
            print("[OK] Rejected hash mismatch")

        raw = json.loads(state_path.read_text(encoding="utf-8"))
        if "master_plan" not in raw:
            print("[FAIL] State file corrupt")
            return 1
        print("[OK] Atomic state file valid JSON")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
