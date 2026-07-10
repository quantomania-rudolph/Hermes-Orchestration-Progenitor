"""WSL-native execution layer for HERMES + DAEDALUS.

Default: orchestrators re-exec inside WSL so every `agent -p` call runs directly
in Linux (no per-spawn wsl.exe bridge). Cursor spawns use run_agent_cli_with_retry.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time
from pathlib import Path, PureWindowsPath

HERMES_ROOT = Path(__file__).resolve().parent
LOOP_DIR = HERMES_ROOT / "main orchestration loop"
DAEDALUS_ROOT = HERMES_ROOT / "daedalus"
REEXEC_FLAG = "HERMES_WSL_NATIVE_REEXEC"


class WSLNativeError(RuntimeError):
    """WSL-native runtime could not be established."""


def is_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text(encoding="utf-8").lower()
    except OSError:
        return False


def wsl_native_enabled() -> bool:
    mode = os.environ.get("HERMES_CURSOR_EXECUTION", "wsl_native").strip().lower()
    if mode in ("win_bridge", "windows", "bridge"):
        return False
    if os.environ.get("HERMES_STRUCTURAL_VERIFY", "0").strip().lower() in {"1", "true", "yes"}:
        return False
    if os.environ.get("HERMES_WSL_NATIVE_DISABLE", "0").strip().lower() in {"1", "true", "yes"}:
        return False
    return True


def to_wsl_path(path: Path) -> str:
    p = path.resolve()
    s = str(p)
    win = PureWindowsPath(s)
    if win.drive:
        drive = win.drive.rstrip(":").lower()
        rest = "/".join(win.parts[1:])
        return f"/mnt/{drive}/{rest}"
    return s.replace("\\", "/")


def wsl_hermes_root() -> str:
    return to_wsl_path(HERMES_ROOT)


def _load_env() -> None:
    try:
        from hermes_secrets import load_local_env
        load_local_env()
    except ImportError:
        pass


def configure_wsl_native_defaults() -> None:
    """Pin WSL-native + retry + serialization defaults."""
    os.environ.setdefault("HERMES_CURSOR_EXECUTION", "wsl_native")
    os.environ.setdefault("HERMES_CURSOR_BACKEND", "cli")
    os.environ.setdefault("DAEDALUS_CURSOR_BACKEND", "cli")
    os.environ.setdefault("CURSOR_SERIALIZE_CALLS", "1")
    os.environ.setdefault("HERMES_WSL_AUTO_RECOVER", "1")
    os.environ.setdefault("CURSOR_MAX_RETRIES", "4")
    os.environ.setdefault("CURSOR_RETRY_BACKOFF_SEC", "2.0")


def wsl_python() -> str:
    """Best Python interpreter inside WSL for orchestrator re-exec."""
    venv = f"{wsl_hermes_root()}/.venv-wsl/bin/python3"
    return venv


def ensure_wsl_venv(*, bootstrap: bool = True) -> str:
    """Return WSL python path; optionally bootstrap .venv-wsl."""
    py = wsl_python()
    if os.name != "nt":
        if Path(py).is_file():
            return py
        return sys.executable

    check = subprocess.run(
        ["wsl", "-e", "bash", "-lc", f'test -x "{py}" && echo OK'],
        capture_output=True, text=True, timeout=30,
    )
    if check.returncode == 0 and "OK" in (check.stdout or ""):
        return py

    if not bootstrap:
        raise WSLNativeError(
            ".venv-wsl missing in WSL. Run: "
            'wsl -e bash "main orchestration loop/run/05_setup_wsl_environment.sh"'
        )

    setup = LOOP_DIR / "run" / "05_setup_wsl_environment.sh"
    wsl_setup = to_wsl_path(setup)
    print("[wsl-native] bootstrapping .venv-wsl (first run)...", flush=True)
    proc = subprocess.run(
        ["wsl", "-e", "bash", wsl_setup],
        cwd=str(HERMES_ROOT),
        timeout=600,
    )
    if proc.returncode != 0:
        raise WSLNativeError(f"WSL setup failed (rc={proc.returncode})")
    return py


def reexec_in_wsl_native() -> None:
    """Re-exec current Python entrypoint inside WSL when on Windows host.
    Handles parent PID sentinel to avoid stale‑process false positives.
    """
    if not wsl_native_enabled():
        return
    if is_wsl() or os.environ.get(REEXEC_FLAG) == "1":
        os.environ[REEXEC_FLAG] = "1"
        configure_wsl_native_defaults()
        return
    if os.name != "nt":
        configure_wsl_native_defaults()
        return

    _load_env()
    configure_wsl_native_defaults()

    script = Path(sys.argv[0]).resolve()
    if not script.is_file():
        return

    py = ensure_wsl_venv(bootstrap=True)
    wsl_script = to_wsl_path(script)
    wsl_cwd = to_wsl_path(Path.cwd())
    root = wsl_hermes_root()
    loop = to_wsl_path(LOOP_DIR)
    daedalus = to_wsl_path(DAEDALUS_ROOT)

    env_file = f"{root}/.env.local"
    args = " ".join(shlex.quote(a) for a in sys.argv[1:])

    # Get Windows parent PID before WSL handoff
    windows_parent_pid = os.getpid()

    inner = (
        f'export {REEXEC_FLAG}=1; '
        f'export HERMES_WSL_NATIVE_PARENT_PID={windows_parent_pid}; '
        f'export HERMES_WSL_NATIVE_WINDOWS_PID={windows_parent_pid}; '
        f'export HERMES_CURSOR_EXECUTION=wsl_native; '
        f'export PATH="$HOME/.local/bin:{root}/.venv-wsl/bin:$PATH"; '
        f'export PYTHONPATH="{root}:{daedalus}:{loop}:$PYTHONPATH"; '
        f'export PYTHONUNBUFFERED=1; '
        f'if [[ -f "{env_file}" ]]; then set -a; '
        f'key_line="$(grep -E \'^\\s*CURSOR_API_KEY=\' "{env_file}" | tail -1 | sed \'s/\\r$//\')"; '
        f'[[ -n "$key_line" ]] && export "$key_line"; '
        f'db_lines="$(grep -E \'^\\s*(DB_|DATABASE_URL)=\' "{env_file}" | sed \'s/\\r$//\')"; '
        f'[[ -n "$db_lines" ]] && export "$db_lines"; '
        f'set +a; fi; '
        f'cd {shlex.quote(wsl_cwd)} && '
        f'{py} {shlex.quote(wsl_script)} {args}'
    )

    print("[wsl-native] re-exec orchestrator inside WSL (direct agent -p, no wsl.exe bridge)",
          flush=True)
    # Write sentinel with parent PID for hygiene
    sentinel_path = HERMES_ROOT / ".wsl_parent_pid"
    try:
        sentinel_path.write_text(str(windows_parent_pid), encoding="utf-8")
    except Exception:
        pass
    proc = subprocess.run(["wsl", "-e", "bash", "-lc", inner])
    raise SystemExit(proc.returncode)


def run_cursor_spawn_preflight(*, ping: bool = True, cwd: Path | None = None) -> list[str]:
    """Pre-spawn health check for Cursor agent CLI via WSL.
    
    Returns list of failure messages (empty = all checks pass).
    Used by hermes_live_stack and verify_campaign_preflight.
    """
    from hermes_cursor_connectivity import probe_cursor_stack
    if cwd is None:
        cwd = Path.cwd()
    report = probe_cursor_stack(run_ping=ping, ping_cwd=cwd)
    if report.ok:
        if ping:
            # RG-A003: Record successful ping timestamp for session dedup
            os.environ["HERMES_CURSOR_PING_TS"] = str(time.time())
            os.environ["HERMES_CURSOR_PING_OK"] = "1"
        return []
    return [f"{c['check']}: {c['detail']}" for c in report.checks if not c['ok']]


def _wsl_reexec_contract() -> str:
    """Document the WSL-native re-exec contract for process hygiene.

    Environment variables set on WSL child:
      HERMES_WSL_NATIVE_REEXEC=1
      HERMES_WSL_NATIVE_PARENT_PID=<Windows parent Python PID>
      HERMES_WSL_NATIVE_WINDOWS_PID=<Windows parent Python PID>
      HERMES_CURSOR_EXECUTION=wsl_native

    Process hygiene expectation:
      After re-exec, find_stale_campaign_pids() should return empty list
      when except_pid includes the Windows parent PID (via HERMES_WSL_NATIVE_PARENT_PID).
      The Windows parent process is intentionally excluded from stale campaign detection
      to avoid false positives during WSL-native re-exec workflow.

    Sentinel file:
      HERMES_ROOT/.wsl_parent_pid contains the Windows parent PID for cross-process
      hygiene coordination (read by INFRA-C process_hygiene on Windows side).
    """
    return (
        "WSL-native re-exec contract: "
        "HERMES_WSL_NATIVE_PARENT_PID and HERMES_WSL_NATIVE_WINDOWS_PID set to Windows parent PID; "
        "hygiene should exclude this PID to prevent false positives. "
        "Sentinel file at HERMES_ROOT/.wsl_parent_pid mirrors the parent PID."
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="WSL-native re-exec environment checker")
    parser.add_argument("--check-env", action="store_true", help="Print re-exec environment status")
    args = parser.parse_args()
    
    if args.check_env:
        print(f"HERMES_WSL_NATIVE_REEXEC={os.environ.get('HERMES_WSL_NATIVE_REEXEC', 'unset')}")
        print(f"HERMES_WSL_NATIVE_PARENT_PID={os.environ.get('HERMES_WSL_NATIVE_PARENT_PID', 'unset')}")
        print(f"HERMES_WSL_NATIVE_WINDOWS_PID={os.environ.get('HERMES_WSL_NATIVE_WINDOWS_PID', 'unset')}")
        print(f"HERMES_CURSOR_EXECUTION={os.environ.get('HERMES_CURSOR_EXECUTION', 'unset')}")
        print(f"is_wsl()={is_wsl()}")
        print(f"os.name={os.name}")
    else:
        print("Usage: python hermes_wsl_native.py --check-env")


