#!/usr/bin/env python3
"""Verify cloud-agent prerequisites (git remote + optional live probe)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parents[1]
HERMES_ROOT = LOOP_DIR.parent
sys.path.insert(0, str(LOOP_DIR))
sys.path.insert(0, str(HERMES_ROOT))

from agents.cloud_git_sync import (  # noqa: E402
    git_remote_url,
    is_git_repo,
    prepare_for_cloud_spawn,
)
from hermes_secrets import load_local_env  # noqa: E402

load_local_env()


def main() -> int:
    print("=== verify_cursor_cloud ===")
    api_key = os.environ.get("CURSOR_API_KEY", "").strip()
    if not api_key:
        print("[FAIL] CURSOR_API_KEY not set")
        return 1
    print("[OK] CURSOR_API_KEY loaded")

    if not is_git_repo(HERMES_ROOT):
        print("[FAIL] No .git — run run/07_setup_git_cloud.bat")
        return 1
    print("[OK] git repository present")

    remote = git_remote_url(HERMES_ROOT)
    if not remote:
        print("[FAIL] No origin remote — add GitHub remote and push")
        return 1
    print(f"[OK] origin remote: {remote}")

    prep = prepare_for_cloud_spawn(HERMES_ROOT)
    if not prep.ok:
        print(f"[FAIL] prepare_for_cloud_spawn: {prep.detail}")
        return 1
    print(f"[OK] {prep.detail}")

    if os.environ.get("HERMES_CLOUD_PROBE", "0").strip().lower() not in {"1", "true", "yes"}:
        print("[OK] Cloud prerequisites met (set HERMES_CLOUD_PROBE=1 for live spawn test)")
        return 0

    os.environ["HERMES_CURSOR_RUNTIME"] = "cloud"
    os.environ["HERMES_T09_RUNTIME"] = "cursor"
    from agents.cursor_sdk import CursorSDK  # noqa: E402

    sdk = CursorSDK()
    try:
        result = sdk.spawn_and_run(
            "Reply with exactly: CLOUD_PING_OK",
            cwd=HERMES_ROOT,
            target_files=[],
        )
        print(f"[OK] Cloud probe status={result.status} runtime={result.runtime}")
        return 0 if result.status not in ("error",) else 1
    except Exception as exc:
        print(f"[FAIL] Cloud probe: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
