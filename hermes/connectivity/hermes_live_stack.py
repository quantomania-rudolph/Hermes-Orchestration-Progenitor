"""Mandatory live execution stack for HERMES + DAEDALUS.

Production runs require:
  1. WSL2 reachable from Windows
  2. Cursor Agent CLI (`agent -p --trust`) with CURSOR_API_KEY
  3. NoLlama on Intel Arc GPU (local Hermes brain)

Set HERMES_STRUCTURAL_VERIFY=1 only for dry structural verification scripts
(verify_connection_flow, etc.) — never for pipeline generation or RSI campaigns.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

HERMES_ROOT = Path(__file__).resolve().parent
LOOP_DIR = HERMES_ROOT / "main orchestration loop"

# TTL for live Cursor ping session cache (RG-A003)
_PING_TTL_SEC = int(os.environ.get("HERMES_CURSOR_PING_TTL_SEC", "60"))


class LiveStackError(RuntimeError):
    """Raised when the mandatory WSL2 + Cursor + Arc stack is not ready."""


def is_structural_verify_only() -> bool:
    return os.environ.get("HERMES_STRUCTURAL_VERIFY", "0").strip().lower() in {
        "1", "true", "yes",
    }


def _recent_ping_ok() -> bool:
    """Check if a live Cursor ping was successful within the TTL window (RG-A003)."""
    if os.environ.get("HERMES_CURSOR_PING_OK") != "1":
        return False
    ts = float(os.environ.get("HERMES_CURSOR_PING_TS", "0") or "0")
    return (time.time() - ts) < _PING_TTL_SEC


def configure_intel_arc_defaults() -> None:
    """Pin local inference and numerics to Intel Arc / XPU."""
    os.environ.setdefault("HERMES_USE_INTEL_XPU", "1")
    os.environ.setdefault("HERMES_FORCE_CPU", "0")
    os.environ.setdefault("HERMES_T09_RUNTIME", "cursor")
    os.environ.setdefault("HERMES_CURSOR_BACKEND", "cli")
    os.environ.setdefault("DAEDALUS_CURSOR_BACKEND", "cli")
    os.environ.setdefault("HERMES_CURSOR_EXECUTION", "wsl_native")
    os.environ.setdefault("CURSOR_SERIALIZE_CALLS", "1")
    os.environ.setdefault("HERMES_WSL_AUTO_RECOVER", "1")
    os.environ.setdefault("CURSOR_MAX_RETRIES", "4")
    os.environ.setdefault("HERMES_REQUIRE_LIVE_CURSOR", "1")
    os.environ.setdefault("DAEDALUS_REQUIRE_LIVE_CURSOR", "1")
    os.environ.setdefault("DAEDALUS_ALLOW_LOCAL_FALLBACK", "0")
    # NoLlama: prefer @GPU model ids (Intel Arc via scripts/run_intel_gpu)
    os.environ.setdefault("HERMES_CHAT_MODEL", "qwen3-14b-int4")
    os.environ.setdefault("HERMES_CURSOR_AGENT_MODEL", "auto")
    os.environ.setdefault("HERMES_CURSOR_MODEL", "auto")
    os.environ.setdefault("CURSOR_SPAWN_TIMEOUT_SECONDS", "600")
    os.environ.setdefault("CURSOR_IDLE_TIMEOUT_SEC", "180")
    os.environ.setdefault("CURSOR_AGENT_START_TIMEOUT_SEC", "90")
    # Preflight ping timeout (cold-start tolerant, default >= 90s per HALT-P2-003)
    os.environ.setdefault("CURSOR_PREFLIGHT_PING_TIMEOUT_SEC", "90")
    os.environ.setdefault("CURSOR_PREFLIGHT_PING_RETRIES", "2")
    os.environ.setdefault("CURSOR_PREFLIGHT_PING_BACKOFF_SEC", "2.0")
    os.environ.setdefault("NOLLAMA_OPENAI_BASE_URL", "http://127.0.0.1:8010/v1")
    os.environ.setdefault("NOLLAMA_HEALTH_URL", "http://127.0.0.1:8010/health")
    os.environ.setdefault("HERMES_REQUIRE_INTEL_ARC", "1")


def _ensure_paths() -> None:
    if str(HERMES_ROOT) not in sys.path:
        sys.path.insert(0, str(HERMES_ROOT))
    if str(LOOP_DIR) not in sys.path:
        sys.path.insert(0, str(LOOP_DIR))


def _try_wsl_recover() -> bool:
    """Last-resort WSL restart when the service returns E_UNEXPECTED."""
    if os.name != "nt" or os.environ.get("HERMES_WSL_AUTO_RECOVER", "1") != "1":
        return False
    try:
        subprocess.run(["wsl", "--shutdown"], capture_output=True, timeout=30)
        time.sleep(5)
        proc = subprocess.run(["wsl", "-e", "true"], capture_output=True, timeout=30)
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def check_wsl2(*, retries: int = 3) -> tuple[bool, str]:
    from hermes_cursor_connectivity import invalidate_wsl_probe_cache
    if os.name != "nt":
        return True, "native POSIX (WSL not required)"
    if not shutil_which("wsl"):
        return False, "wsl.exe not found — install WSL2"
    last_msg = ""
    for attempt in range(1, retries + 1):
        invalidate_wsl_probe_cache()
        try:
            proc = subprocess.run(["wsl", "-e", "true"], capture_output=True, text=True, timeout=30)
            if proc.returncode != 0:
                last_msg = f"WSL probe failed: {proc.stderr.strip() or proc.returncode}"
                time.sleep(1.5 * attempt)
                continue
        except (OSError, subprocess.TimeoutExpired) as exc:
            last_msg = f"WSL unreachable: {exc}"
            time.sleep(1.5 * attempt)
            continue
        try:
            proc = subprocess.run(
                ["wsl", "-e", "bash", "-lc", "export PATH=\"$HOME/.local/bin:$PATH\"; which agent"],
                capture_output=True, text=True, timeout=35,
            )
            if proc.returncode != 0 or not proc.stdout.strip():
                last_msg = "Cursor agent CLI not in WSL (~/.local/bin/agent)"
                time.sleep(1.5 * attempt)
                continue
        except (OSError, subprocess.TimeoutExpired) as exc:
            last_msg = f"WSL agent probe failed: {exc}"
            time.sleep(1.5 * attempt)
            continue
        return True, "WSL2 + agent CLI present"
    if _try_wsl_recover():
        return check_wsl2(retries=2)
    return False, last_msg or "WSL probe failed"


def shutil_which(cmd: str) -> str | None:
    from shutil import which
    return which(cmd)


def check_cursor_api_key() -> tuple[bool, str]:
    key = os.environ.get("CURSOR_API_KEY", "").strip()
    if not key:
        try:
            from hermes_secrets import load_local_env
            load_local_env()
            key = os.environ.get("CURSOR_API_KEY", "").strip()
        except ImportError:
            pass
    if not key:
        return False, "CURSOR_API_KEY missing — add to .env.local"
    return True, "CURSOR_API_KEY configured"


def check_cursor_cli_backend() -> tuple[bool, str]:
    """Probe the production daedalus CLI module without the Hermes shim loop."""
    from hermes_cursor_connectivity import _import_daedalus_cli

    try:
        cli_mod = _import_daedalus_cli()
    except Exception as exc:
        return False, f"Cursor CLI import failed: {exc}"
    if not cli_mod.cli_backend_enabled():
        backend = os.environ.get("HERMES_CURSOR_BACKEND", "cli")
        return False, f"Cursor CLI backend disabled (HERMES_CURSOR_BACKEND={backend})"
    return True, "Cursor CLI backend enabled"


def check_nollama_arc() -> tuple[bool, str]:
    from hermes_nollama import ensure_nollama_running

    ok, detail = ensure_nollama_running(timeout_sec=180.0)
    if ok:
        return True, detail
    return False, detail


def enforce_hermes_live_stack(*, require_nollama: bool = True) -> None:
    """Fail fast before HERMES orchestrator runs without full AI stack."""
    from hermes_secrets import load_local_env

    load_local_env()
    configure_intel_arc_defaults()

    if is_structural_verify_only():
        return

    if os.environ.get("HERMES_DRY_RUN", "0").strip().lower() in {"1", "true", "yes"}:
        raise LiveStackError(
            "HERMES_DRY_RUN is forbidden for production runs. "
            "Use HERMES_STRUCTURAL_VERIFY=1 for structural-only verification."
        )
    if os.environ.get("HERMES_SKIP_CURSOR", "0").strip().lower() in {"1", "true", "yes"}:
        raise LiveStackError("HERMES_SKIP_CURSOR is forbidden — WSL2 Cursor is mandatory")

    failures: list[str] = []
    for ok, msg in (check_wsl2(), check_cursor_api_key(), check_cursor_cli_backend()):
        if not ok:
            failures.append(msg)

    try:
        from hermes_wsl_native import run_cursor_spawn_preflight
        spawn_failures = run_cursor_spawn_preflight(ping=True)
        failures.extend(spawn_failures)
    except Exception as exc:
        failures.append(f"spawn preflight: {exc}")

    if require_nollama:
        ok, msg = check_nollama_arc()
        if not ok:
            failures.append(msg)

    if failures:
        raise LiveStackError(
            "LIVE STACK INCOMPLETE — cannot run without WSL2 + Cursor + Intel Arc:\n  - "
            + "\n  - ".join(failures)
        )


def enforce_daedalus_live_stack() -> None:
    """Fail fast before DAEDALUS campaigns without live Cursor."""
    from hermes_secrets import load_local_env
    from tools.lifecycle.stage_heartbeat import log_stage

    load_local_env()
    configure_intel_arc_defaults()

    if is_structural_verify_only():
        return

    if os.environ.get("DAEDALUS_ALLOW_LOCAL_FALLBACK", "0").strip().lower() in {"1", "true", "yes"}:
        raise LiveStackError(
            "DAEDALUS_ALLOW_LOCAL_FALLBACK is forbidden — live Cursor mutations are mandatory"
        )

    # RG-A003: Skip live ping if already verified within TTL
    if _recent_ping_ok():
        ttl = _PING_TTL_SEC
        log_stage("live_stack_ping", f"skipped ttl={ttl} preflight_ping_skipped=true")
        # Still run non-ping checks (WSL2, api_key, cli backend)
        daedalus_root = HERMES_ROOT / "daedalus"
        failures: list[str] = []
        for ok, msg in (check_wsl2(), check_cursor_api_key(), check_cursor_cli_backend()):
            if not ok:
                failures.append(msg)
        if failures:
            raise LiveStackError(
                "DAEDALUS LIVE STACK INCOMPLETE:\n  - " + "\n  - ".join(failures)
            )
        os.environ["DAEDALUS_STACK_VERIFIED"] = "1"
        return

    daedalus_root = HERMES_ROOT / "daedalus"
    failures: list[str] = []
    for ok, msg in (check_wsl2(), check_cursor_api_key(), check_cursor_cli_backend()):
        if not ok:
            failures.append(msg)

    try:
        from hermes_wsl_native import run_cursor_spawn_preflight
        spawn_failures = run_cursor_spawn_preflight(ping=True, cwd=daedalus_root)
        failures.extend(spawn_failures)
    except Exception as exc:
        failures.append(f"spawn preflight: {exc}")

    for mod in list(sys.modules):
        if mod == "agents" or mod.startswith("agents."):
            del sys.modules[mod]
        elif mod == "tools" or mod.startswith("tools."):
            del sys.modules[mod]
        elif mod == "config" or mod.startswith("config."):
            del sys.modules[mod]
    if str(HERMES_ROOT) not in sys.path:
        sys.path.insert(0, str(HERMES_ROOT))
    if str(daedalus_root) not in sys.path:
        sys.path.insert(0, str(daedalus_root))
    elif sys.path[0] != str(daedalus_root):
        sys.path.remove(str(daedalus_root))
        sys.path.insert(0, str(daedalus_root))

    import importlib

    cursor_gate = importlib.import_module("tools.lifecycle.r37_cursor_gate")
    preflight = cursor_gate.CursorGate().preflight()
    if preflight.data.get("mode") != "LIVE":
        failures.append(preflight.message)

    if failures:
        raise LiveStackError(
            "DAEDALUS LIVE STACK INCOMPLETE:\n  - " + "\n  - ".join(failures)
        )
    os.environ["DAEDALUS_STACK_VERIFIED"] = "1"


def hermes_cursor_gate_ok() -> bool:
    """True when T11-equivalent live Cursor preflight passes."""
    try:
        enforce_hermes_live_stack(require_nollama=False)
        _ensure_paths()
        from tools.agents.t11_cursor_gate import CursorAvailabilityGate

        gate = CursorAvailabilityGate().run(budget_ok=True, skip=False)
        return gate.status.value == "CURSOR_OK"
    except LiveStackError:
        return False
