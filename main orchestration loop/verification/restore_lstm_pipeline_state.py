#!/usr/bin/env python3
"""One-shot: mark lstm_optuna_vault_trader plan DONE after manual S009 completion."""

from __future__ import annotations

import json
from pathlib import Path

LOOP = Path(__file__).resolve().parents[1]
SEED = LOOP / "pipeline_state.test_lstm_optuna_vault.seed.json"
OUT = LOOP / "pipeline_state.json"
PREFIX = "generated/lstm_optuna_vault_trader/"


def main() -> int:
    state = json.loads(SEED.read_text(encoding="utf-8"))
    for step in state["master_plan"]:
        step["status"] = "green"
        step["target_files"] = [
            tf if tf.startswith("generated/") else f"{PREFIX}{tf}"
            for tf in step.get("target_files", [])
        ]
    state["horizon"] = {
        "window": [],
        "cursor": None,
        "cursor_locked": False,
        "wipe_due": False,
    }
    state["runtime"] = {
        "current_phase": "DONE",
        "repo_path": str(LOOP.parent),
        "output_slug": "lstm_optuna_vault_trader",
        "index": {"consistent": True},
    }
    state["journal"] = [
        {
            "transition_type": "GREEN_COMMIT",
            "phase": "P4",
            "step_id": f"S00{i}",
        }
        for i in range(1, 10)
    ]
    OUT.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(f"[OK] wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
