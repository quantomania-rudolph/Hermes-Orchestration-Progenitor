#!/usr/bin/env bash
set -euo pipefail
HERMES_ROOT="/mnt/c/Users/Rudol/Desktop/Hermes_Orchestration"
export PATH="$HOME/.local/bin:$HERMES_ROOT/.venv-wsl/bin:$PATH"
cd "$HERMES_ROOT"
exec "$HERMES_ROOT/.venv-wsl/bin/python" - <<'PY'
import os
import sys
from pathlib import Path

sys.path.insert(0, "main orchestration loop")
sys.path.insert(0, ".")
from hermes_secrets import load_local_env

load_local_env()
from agents.cursor_sdk import CursorSDK

sdk = CursorSDK()
result = sdk.spawn_and_run(
    "Reply with exactly: SDK_WSL_OK",
    cwd=Path("."),
    target_files=[],
)
print(f"status={result.status} runtime={result.runtime}")
print(result.transcript[-300:])
if result.status in ("error",) or "SDK_WSL_OK" not in result.transcript:
    raise SystemExit(1)
print("[OK] Cursor SDK live spawn from WSL")
PY
