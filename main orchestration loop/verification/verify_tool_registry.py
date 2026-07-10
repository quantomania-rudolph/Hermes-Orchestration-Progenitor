#!/usr/bin/env python3
"""Verify T25 static tool registry matches docs (30 tools, phase matrix)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOOP_DIR))

from config.loop_config import STATIC_TOOL_REGISTRY  # noqa: E402
from tools.meta.t25_tool_registry import ToolRegistry  # noqa: E402
from tools.common import Phase  # noqa: E402


EXPECTED_IDS = {f"T{i:02d}" for i in range(1, 31)}


def main() -> int:
    print("=== verify_tool_registry ===")
    payload = json.loads(STATIC_TOOL_REGISTRY.read_text(encoding="utf-8"))
    ids = {t["id"] for t in payload.get("tools", [])}
    missing = EXPECTED_IDS - ids
    extra = ids - EXPECTED_IDS
    if missing:
        print(f"[FAIL] Missing tool IDs: {sorted(missing)}")
        return 1
    if extra:
        print(f"[FAIL] Unexpected tool IDs: {sorted(extra)}")
        return 1
    print(f"[OK] All 30 tool IDs present")

    reg = ToolRegistry(STATIC_TOOL_REGISTRY, LOOP_DIR / "system_tools" / "registry.json")
    # T09 only in P2
    rej = reg.validate_tool_call("T09", Phase.P1, {})
    if rej is None:
        print("[FAIL] T09 should be rejected in P1")
        return 1
    print(f"[OK] T09 correctly blocked in P1: {rej.reason}")

    ok = reg.validate_tool_call("T07", Phase.P0, {})
    if ok is not None:
        print(f"[FAIL] T07 should be allowed in P0: {ok.reason}")
        return 1
    print("[OK] T07 allowed in P0")

    cursor_tools = [tid for tid, e in reg.tools.items() if e.get("cursor_sdk_required")]
    if set(cursor_tools) != {"T09", "T10", "T24"}:
        print(f"[FAIL] Cursor SDK tools mismatch: {cursor_tools}")
        return 1
    print(f"[OK] Cursor-dependent tools: {cursor_tools}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
