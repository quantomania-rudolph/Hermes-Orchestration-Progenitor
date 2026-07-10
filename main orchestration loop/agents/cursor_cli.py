"""Cursor Agent connectivity via the `agent` CLI over WSL2.

Delegates to daedalus/agents/cursor_cli.py for anti-stall watchdog + WSL-native
direct invocation when running inside WSL.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERMES_ROOT = Path(__file__).resolve().parents[2]
_DAEDALUS = _HERMES_ROOT / "daedalus"


def _daedalus_cli():
    saved = sys.path[:]
    try:
        while str(_DAEDALUS) in sys.path:
            sys.path.remove(str(_DAEDALUS))
        sys.path.insert(0, str(_DAEDALUS))
        from agents import cursor_cli as mod
        return mod
    finally:
        sys.path[:] = saved


_cli = _daedalus_cli()

CursorCLIError = _cli.CursorCLIError
is_wsl = _cli.is_wsl
wsl_exe_available = _cli.wsl_exe_available
cli_backend_enabled = _cli.cli_backend_enabled
new_run_id = _cli.new_run_id
run_agent_cli = _cli.run_agent_cli
