#!/usr/bin/env python3
"""Complete a session stuck after all steps are green (P5 T10 hang)."""

from __future__ import annotations

import sys
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parents[1]
HERMES_ROOT = LOOP_DIR.parent
if str(LOOP_DIR) not in sys.path:
    sys.path.insert(0, str(LOOP_DIR))
if str(HERMES_ROOT) not in sys.path:
    sys.path.insert(0, str(HERMES_ROOT))

from orchestrator.bootstrap import build_context  # noqa: E402
from orchestrator.phases.phase5_reconcile import run_phase5  # noqa: E402
from tools.governance.output_paths import finalize_completed_session  # noqa: E402


def main() -> int:
    ctx = build_context(HERMES_ROOT)
    state = ctx.state_manager.read()
    if not ctx.horizon.project_complete(state):
        print("[FAIL] Not all steps green — cannot finalize")
        return 1
    state = run_phase5(ctx, state, reason="project_complete")
    finalize_completed_session(ctx, state)
    print("[session] PROJECT COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
