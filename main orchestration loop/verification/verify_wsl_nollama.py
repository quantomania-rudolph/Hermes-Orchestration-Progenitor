#!/usr/bin/env python3
"""Verify NoLlama reachable from current runtime (Windows or WSL)."""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parents[1]
HERMES_ROOT = LOOP_DIR.parent
sys.path.insert(0, str(HERMES_ROOT))

from hermes_secrets import load_local_env  # noqa: E402

load_local_env()


def _probe(base: str) -> bool:
    try:
        req = urllib.request.Request(f"{base.rstrip('/')}/health", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def main() -> int:
    print("=== verify_wsl_nollama ===")
    base = os.environ.get("NOLLAMA_OPENAI_BASE_URL", "http://127.0.0.1:8000/v1")
    health_base = base.replace("/v1", "")
    if _probe(health_base):
        print(f"[OK] NoLlama health reachable at {health_base}")
        return 0
    print(f"[WARN] NoLlama not reachable at {health_base}")
    try:
        from agents.cursor_cli import is_wsl
    except ImportError:
        is_wsl = lambda: False  # type: ignore
    if is_wsl():
        print("  Fix: run 08_enable_wsl_nollama_portproxy.bat as Administrator on Windows")
        print("  Then re-run from WSL with NOLLAMA_OPENAI_BASE_URL=http://<gateway>:8000/v1")
    else:
        print("  Fix: start scripts\\run_intel_gpu\\01_start_nollama.bat")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
