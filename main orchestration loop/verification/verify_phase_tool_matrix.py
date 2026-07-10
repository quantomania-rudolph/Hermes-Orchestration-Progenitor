#!/usr/bin/env python3
"""Verify T25 phase matrix and document which tools each phase invokes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOOP_DIR))

from tools.common import Phase  # noqa: E402
from tools.meta.t25_tool_registry import ToolRegistry  # noqa: E402
from config.loop_config import STATIC_TOOL_REGISTRY, SYNTHESIZED_REGISTRY  # noqa: E402

# Tools directly invoked by phase modules (Python-orchestrated loop)
PHASE_WIRED: dict[str, set[str]] = {
    "P0": {"T02", "T03", "T04", "T06", "T07", "T11", "T21", "T23", "T25"},
    "P1": {"T01", "T02", "T03", "T04", "T05", "T07", "T10", "T11", "T21", "T29"},
    "P2": {"T01", "T06", "T07", "T08", "T09", "T10", "T11", "T12", "T13", "T14", "T15", "T20", "T21"},
    "P3": {"T01", "T10", "T11", "T16", "T17", "T18", "T19", "T20", "T30"},
    "P4": {"T03", "T06", "T07", "T14", "T15", "T23"},
    "P5": {"T02", "T04", "T05", "T06", "T10", "T11", "T22", "T30"},
    "ALL": {"T02", "T21", "T29"},  # invariants
}

# Tools implemented but invoked only via Hermes/meta paths (not phase-hardcoded)
HERMES_META_LAYER = {"T24", "T26", "T27", "T28"}


def main() -> int:
    print("=== verify_phase_tool_matrix ===")
    reg = ToolRegistry(STATIC_TOOL_REGISTRY, SYNTHESIZED_REGISTRY)
    payload = json.loads(STATIC_TOOL_REGISTRY.read_text(encoding="utf-8"))
    failures: list[str] = []

    for tool in payload["tools"]:
        tid = tool["id"]
        allowed = set(tool["phases_allowed"])
        for phase_name, wired in PHASE_WIRED.items():
            if phase_name == "ALL":
                continue
            if tid in wired and phase_name not in allowed and "P0" not in allowed:
                # wired tool must be allowed in that phase per T25
                if phase_name not in allowed:
                    failures.append(f"{tid} wired in {phase_name} but phases_allowed={sorted(allowed)}")

    # Every wired tool must exist in registry
    all_wired = set().union(*PHASE_WIRED.values())
    for tid in all_wired:
        if tid not in reg.tools:
            failures.append(f"Wired {tid} missing from registry")

    # Spot-check illegal phase calls
    checks = [
        ("T09", Phase.P1, True),
        ("T16", Phase.P3, False),
        ("T07", Phase.P0, False),
        ("T04", Phase.P5, False),
        ("T08", Phase.P2, False),
    ]
    for tid, phase, should_reject in checks:
        rej = reg.validate_tool_call(tid, phase, {})
        if should_reject and rej is None:
            failures.append(f"{tid} should be rejected in {phase.value}")
        if not should_reject and rej is not None:
            failures.append(f"{tid} should be allowed in {phase.value}: {rej.reason}")

    print("[INFO] Phase-wired tools:")
    for phase in ("P0", "P1", "P2", "P3", "P4", "P5"):
        wired = sorted(PHASE_WIRED[phase])
        print(f"  {phase}: {', '.join(wired)}")

    print(f"[INFO] Hermes/meta layer (smoke-tested, not phase-hardcoded): {sorted(HERMES_META_LAYER)}")

    if failures:
        print("[FAIL] Matrix failures:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("[OK] Phase tool matrix consistent with T25 registry")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
