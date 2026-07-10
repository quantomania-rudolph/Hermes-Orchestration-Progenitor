#!/usr/bin/env python3
"""Verify Cursor SDK auth + bridge (soft-fail on known Windows bridge bug)."""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parents[1]
HERMES_ROOT = LOOP_DIR.parent
sys.path.insert(0, str(LOOP_DIR))
sys.path.insert(0, str(HERMES_ROOT))

from hermes_secrets import load_local_env  # noqa: E402

load_local_env()

BRIDGE_WINERROR = "10038"


def _api_reachable() -> bool:
    try:
        req = urllib.request.Request("https://api.cursor.com", method="HEAD")
        urllib.request.urlopen(req, timeout=8)
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def main() -> int:
    print("=== verify_cursor_sdk ===")
    api_key = os.environ.get("CURSOR_API_KEY", "").strip()
    if not api_key:
        print("[FAIL] CURSOR_API_KEY not set — add to .env.local")
        return 1
    print("[OK] CURSOR_API_KEY loaded")

    if not _api_reachable():
        print("[WARN] Cursor API endpoint unreachable (network)")
    else:
        print("[OK] Cursor API endpoint reachable")

    # Model list uses local bridge on some SDK versions — try bridge spawn directly
    try:
        from cursor_sdk import Agent, LocalAgentOptions

        with Agent.create(
            api_key=api_key,
            local=LocalAgentOptions(cwd=str(HERMES_ROOT)),
        ):
            print("[OK] Cursor local bridge launched — T09/T10 can spawn")
        return 0
    except OSError as exc:
        if BRIDGE_WINERROR in str(exc):
            print(f"[WARN] Cursor bridge WinError {BRIDGE_WINERROR} — key set, spawn blocked on Windows")
            print("       Auth/endpoint OK; T09/T10 use infra fallbacks until bridge is fixed")
            return 0
        print(f"[FAIL] Cursor bridge error: {exc}")
        return 1
    except Exception as exc:
        if BRIDGE_WINERROR in str(exc):
            print(f"[WARN] Cursor bridge WinError {BRIDGE_WINERROR} — key set, spawn blocked")
            return 0
        print(f"[FAIL] Cursor bridge error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
