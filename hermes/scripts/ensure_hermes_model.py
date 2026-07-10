#!/usr/bin/env python3
"""
Verify NoLlama is up and the configured chat model is loaded.

  python ensure_hermes_model.py --check
  python ensure_hermes_model.py          # check + print install hints if down
"""

from __future__ import annotations

import argparse
import os

from hermes_config import (
    HERMES_CHAT_MODEL_DEFAULT,
    NOLLAMA_HEALTH_URL,
    NOLLAMA_HOME,
)
from hermes_nollama import nollama_health, resolve_chat_model

REQUESTED_MODEL = os.environ.get("HERMES_CHAT_MODEL", HERMES_CHAT_MODEL_DEFAULT)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check NoLlama + Hermes chat model.")
    parser.add_argument("--check", action="store_true", help="Exit 1 if not ready.")
    args = parser.parse_args()

    health = nollama_health()
    if health is None:
        print("[fail] NoLlama health endpoint not reachable:", NOLLAMA_HEALTH_URL)
        print("       Local server issue (not internet). Try:")
        print("         scripts\\run_intel_gpu\\03_daily_setup.bat")
        print("       Or: scripts\\run_intel_gpu\\01_start_nollama.bat")
        return 1

    print(f"[ok] NoLlama health: {health.get('status', health)}")

    resolved = resolve_chat_model(REQUESTED_MODEL, prefer_device="GPU")
    if resolved:
        print(f"[ok] Chat model available: {resolved} (requested: {REQUESTED_MODEL})")
        return 0

    print(f"[warn] Model '{REQUESTED_MODEL}' not listed in /v1/models or /api/tags")
    from hermes_nollama import listed_model_ids

    print("       Loaded models:", ", ".join(listed_model_ids()) or "(none)")
    print("       Re-run scripts\\install_models\\02_download_qwen14b_intel_gpu.bat")
    print("       Or set HERMES_CHAT_MODEL to a loaded model name.")
    return 1 if args.check else 0


if __name__ == "__main__":
    raise SystemExit(main())
