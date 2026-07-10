"""Shared offline / NoLlama preflight for verification scripts."""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERMES_ROOT = Path(__file__).resolve().parents[2]
if str(HERMES_ROOT) not in sys.path:
    sys.path.insert(0, str(HERMES_ROOT))


def skip_unless_nollama(test_name: str) -> bool:
    if os.environ.get("HERMES_SKIP_HERMES_BRAIN", "").strip().lower() in {"1", "true", "yes"}:
        print(f"[SKIP] {test_name} — HERMES_SKIP_HERMES_BRAIN=1")
        return True
    try:
        from hermes_nollama import nollama_health

        health = nollama_health()
        if health is None:
            print(f"[SKIP] {test_name} — NoLlama unreachable")
            return True
        status = str((health or {}).get("status", "")).lower()
        if status not in {"", "ok", "ready"}:
            print(f"[SKIP] {test_name} — NoLlama status={status!r}")
            return True
    except Exception as exc:
        print(f"[SKIP] {test_name} — NoLlama probe failed: {exc}")
        return True
    return False
