#!/usr/bin/env python3
"""Pre-launch cursor-sdk bridge with extended discovery timeout for /mnt/c workspaces."""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parents[1]
HERMES_ROOT = LOOP_DIR.parent
sys.path.insert(0, str(LOOP_DIR))
sys.path.insert(0, str(HERMES_ROOT))

from hermes_secrets import load_local_env  # noqa: E402

load_local_env()

from cursor_sdk._bridge import Bridge  # noqa: E402
from cursor_sdk.types import LocalAgentOptions  # noqa: E402

ENV_PATH = LOOP_DIR / "state" / "wsl_bridge.env"
TIMEOUT = float(os.environ.get("HERMES_BRIDGE_DISCOVERY_TIMEOUT_SEC", "120"))


def main() -> int:
    root = Path(os.environ.get("HERMES_WORKSPACE_ROOT", str(HERMES_ROOT))).resolve()
    bridge = Bridge.launch(
        workspace=str(root),
        timeout=TIMEOUT,
        local=LocalAgentOptions(cwd=str(root)),
    )
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    ENV_PATH.write_text(
        f"CURSOR_SDK_BRIDGE_URL={bridge.endpoint.url}\n"
        f"CURSOR_SDK_BRIDGE_TOKEN={bridge.endpoint.auth_token}\n",
        encoding="utf-8",
    )
    print(f"[bridge] ready url={bridge.endpoint.url} timeout={TIMEOUT}s")

    def _shutdown(*_args: object) -> None:
        bridge.close()
        ENV_PATH.unlink(missing_ok=True)
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    import time

    while True:
        time.sleep(3600)


if __name__ == "__main__":
    raise SystemExit(main())
