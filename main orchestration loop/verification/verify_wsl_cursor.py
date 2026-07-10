#!/usr/bin/env python3
"""Verify Cursor CLI + SDK local bridge inside WSL."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parents[1]
HERMES_ROOT = LOOP_DIR.parent
sys.path.insert(0, str(LOOP_DIR))
sys.path.insert(0, str(HERMES_ROOT))

from hermes_secrets import load_local_env  # noqa: E402

load_local_env()


def main() -> int:
    print("=== verify_wsl_cursor ===")
    venv_py = HERMES_ROOT / ".venv-wsl" / "bin" / "python"
    python = str(venv_py) if venv_py.is_file() else sys.executable

    proc = subprocess.run(
        ["agent", "--version"],
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{os.environ.get('HOME', '')}/.local/bin:" + os.environ.get("PATH", "")},
    )
    if proc.returncode != 0:
        print(f"[FAIL] agent CLI: {proc.stderr.strip() or proc.stdout.strip()}")
        return 1
    print(f"[OK] agent CLI {proc.stdout.strip()}")

    try:
        import cursor_sdk  # noqa: F401
    except ImportError:
        print("[FAIL] cursor-sdk not installed in WSL venv")
        return 1
    print("[OK] cursor-sdk importable")

    api_key = os.environ.get("CURSOR_API_KEY", "").strip()
    if not api_key:
        print("[FAIL] CURSOR_API_KEY not set")
        return 1
    print("[OK] CURSOR_API_KEY loaded")

    from cursor_sdk import Agent, LocalAgentOptions
    from cursor_sdk.errors import CursorSDKError

    model = os.environ.get("HERMES_CURSOR_MODEL", "composer-2.5")
    from agents.cursor_cli import cli_backend_enabled, run_agent_cli

    if cli_backend_enabled():
        status, transcript, rc = run_agent_cli(
            "Reply with exactly: WSL_CURSOR_OK",
            cwd=HERMES_ROOT,
            api_key=api_key,
            timeout_sec=120.0,
        )
        if status == "finished" and "WSL_CURSOR_OK" in transcript:
            print("[OK] Cursor agent CLI backend works (HERMES_CURSOR_BACKEND=cli/auto+WSL)")
            return 0
        print(f"[FAIL] agent CLI probe rc={rc}: {transcript[:400]}")
        return 1

    if os.environ.get("CURSOR_SDK_BRIDGE_URL") and os.environ.get("CURSOR_SDK_BRIDGE_TOKEN"):
        print("[OK] Reusing pre-launched CURSOR_SDK_BRIDGE_URL")
        with Agent.create(
            api_key=api_key,
            model=model,
            local=LocalAgentOptions(cwd=str(HERMES_ROOT)),
        ):
            print(f"[OK] Cursor SDK local bridge works (model={model})")
        return 0

    attempts = int(os.environ.get("HERMES_WSL_BRIDGE_RETRIES", "3"))
    last_err: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with Agent.create(
                api_key=api_key,
                model=model,
                local=LocalAgentOptions(cwd=str(HERMES_ROOT)),
            ):
                print(f"[OK] Cursor SDK local bridge works (model={model})")
            last_err = None
            break
        except (CursorSDKError, OSError) as exc:
            last_err = exc
            print(f"[WARN] bridge attempt {attempt}/{attempts}: {exc}")
            subprocess.run(["pkill", "-f", "cursor-sdk-bridge"], check=False)
            import time

            time.sleep(3)
    if last_err is not None:
        raise last_err

    if os.environ.get("HERMES_WSL_AGENT_PROBE", "0").strip().lower() in {"1", "true", "yes"}:
        probe = subprocess.run(
            ["agent", "-p", "Reply with exactly: WSL_AGENT_OK"],
            capture_output=True,
            text=True,
            cwd=str(HERMES_ROOT),
            env={**os.environ, "CURSOR_API_KEY": api_key, "PATH": f"{os.environ.get('HOME', '')}/.local/bin:" + os.environ.get("PATH", "")},
            timeout=120,
        )
        out = (probe.stdout or "") + (probe.stderr or "")
        if probe.returncode == 0 and "WSL_AGENT_OK" in out:
            print("[OK] agent -p CLI probe succeeded")
        else:
            print(f"[FAIL] agent -p probe: {out[:500]}")
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
