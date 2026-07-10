"""Shared Cursor CLI connectivity for HERMES and DAEDALUS.

Provides resilient WSL2 `agent -p --trust` access with:
  * cache invalidation after failures
  * exponential-backoff retries on retryable errors
  * pre-spawn health probes (WSL, agent binary, API key)
  * port-agnostic operation — Cursor Agent uses cloud API; local NoLlama ports
    are probed separately and do not gate Cursor CLI availability.
  * Cold-start timeout + retry (CURSOR_PREFLIGHT_PING_TIMEOUT_SEC, CURSOR_PREFLIGHT_PING_RETRIES)

Both orchestrators import this module from the Hermes repo root.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


class PreflightError(RuntimeError):
    """Preflight check failed with classified reason."""
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


class CursorConnectivityError(RuntimeError):
    """Cursor stack unreachable after all retries."""


@dataclass
class CursorHealthReport:
    ok: bool
    wsl_ok: bool = False
    agent_ok: bool = False
    api_key_ok: bool = False
    backend_ok: bool = False
    ping_ok: bool = False
    detail: str = ""
    checks: list[dict[str, Any]] = field(default_factory=list)


def invalidate_wsl_probe_cache() -> None:
    """Force re-probe of WSL availability (both Hermes and DAEDALUS caches)."""
    for name, mod in list(sys.modules.items()):
        if name.endswith("cursor_cli") and hasattr(mod, "_WSL_PROBE_CACHE"):
            mod._WSL_PROBE_CACHE = None  # type: ignore[attr-defined]


def _load_env() -> None:
    try:
        from hermes_secrets import load_local_env
        load_local_env()
    except ImportError:
        pass


def _max_retries() -> int:
    return max(1, int(os.environ.get("CURSOR_MAX_RETRIES", "4")))


def _retry_backoff_sec(attempt: int) -> float:
    base = float(os.environ.get("CURSOR_RETRY_BACKOFF_SEC", "2.0"))
    return base * (2 ** max(0, attempt - 1))


def _ping_timeout() -> float:
    return float(os.environ.get("CURSOR_PING_TIMEOUT_SEC", "45"))


def _spawn_timeout() -> float:
    return float(os.environ.get(
        "CURSOR_SPAWN_TIMEOUT_SECONDS",
        os.environ.get("DAEDALUS_CURSOR_SPAWN_TIMEOUT", "600"),
    ))


def _preflight_ping_timeout() -> float:
    """Preflight ping timeout for cold-start resilience (HALT-P2-003).
    Default >= 90 seconds to accommodate cold agent CLI startup."""
    return float(os.environ.get("CURSOR_PREFLIGHT_PING_TIMEOUT_SEC", "90"))


def _preflight_ping_retries() -> int:
    """Number of preflight ping attempts (including initial)."""
    return max(1, int(os.environ.get("CURSOR_PREFLIGHT_PING_RETRIES", "2")))


def _preflight_ping_backoff_sec(attempt: int) -> float:
    """Exponential backoff for preflight ping retries."""
    base = float(os.environ.get("CURSOR_PREFLIGHT_PING_BACKOFF_SEC", "3.0"))
    return base * (2 ** max(0, attempt - 1))


def _import_daedalus_cli():
    """Import daedalus cursor_cli without Hermes loop shadowing agents."""
    import sys
    hermes = Path(__file__).resolve().parent
    daedalus = hermes / "daedalus"
    saved = sys.path[:]
    try:
        while str(daedalus) in sys.path:
            sys.path.remove(str(daedalus))
        sys.path.insert(0, str(daedalus))
        from agents import cursor_cli as cli_mod
        return cli_mod
    finally:
        sys.path[:] = saved


def probe_cursor_stack(
    *, run_ping: bool = False, ping_cwd: Path | None = None,
    ping_timeout_sec: float | None = None
) -> CursorHealthReport:
    """Full stack probe: WSL + agent binary + API key + optional live ping.

    Args:
        run_ping: Whether to run live ping check
        ping_cwd: Working directory for ping
        ping_timeout_sec: Preflight ping timeout (default: CURSOR_PREFLIGHT_PING_TIMEOUT_SEC or 90s)
    """
    _load_env()
    checks: list[dict[str, Any]] = []
    report = CursorHealthReport(ok=False)

    try:
        from hermes_live_stack import check_wsl2
        wsl_ok, wsl_msg = check_wsl2()
    except Exception as exc:
        wsl_ok, wsl_msg = False, str(exc)
    report.wsl_ok = wsl_ok
    checks.append({"check": "wsl2", "ok": wsl_ok, "detail": wsl_msg})

    key = os.environ.get("CURSOR_API_KEY", "").strip()
    report.api_key_ok = bool(key)
    checks.append({"check": "api_key", "ok": report.api_key_ok,
                   "detail": "configured" if report.api_key_ok else "missing"})

    backend_ok = False
    backend_msg = "unknown"
    try:
        cli_mod = _import_daedalus_cli()
        backend_ok = cli_mod.cli_backend_enabled()
        backend_msg = os.environ.get("HERMES_CURSOR_BACKEND",
                                     os.environ.get("DAEDALUS_CURSOR_BACKEND", "cli"))
    except Exception as exc:
        backend_msg = str(exc)
    report.backend_ok = backend_ok
    checks.append({"check": "cli_backend", "ok": backend_ok, "detail": backend_msg})

    agent_ok = False
    agent_msg = ""
    if wsl_ok and os.name == "nt":
        try:
            proc = subprocess.run(
                ["wsl", "-e", "bash", "-lc",
                 'export PATH="$HOME/.local/bin:$PATH"; command -v agent && agent --version 2>/dev/null | head -1'],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
            )
            agent_ok = proc.returncode == 0 and "agent" in (proc.stdout or "")
            agent_msg = (proc.stdout or proc.stderr or "").strip()[:200]
        except (OSError, subprocess.TimeoutExpired) as exc:
            agent_msg = str(exc)
    elif wsl_ok:
        from shutil import which
        agent_ok = which("agent") is not None
        agent_msg = "agent in PATH" if agent_ok else "agent not in PATH"
    report.agent_ok = agent_ok
    checks.append({"check": "agent_binary", "ok": agent_ok, "detail": agent_msg})

    report.ping_ok = True
    if run_ping and report.wsl_ok and report.api_key_ok and report.backend_ok and report.agent_ok:
        timeout = ping_timeout_sec if ping_timeout_sec is not None else _preflight_ping_timeout()
        ping_ok, ping_detail = _cursor_ping(cwd=ping_cwd or Path.cwd(), timeout_sec=timeout)
        report.ping_ok = ping_ok
        checks.append({"check": "live_ping", "ok": ping_ok, "detail": ping_detail[:500]})

    report.checks = checks
    report.ok = all(c["ok"] for c in checks)
    report.detail = "; ".join(
        f"{c['check']}={'OK' if c['ok'] else 'FAIL'}" for c in checks)
    return report


def ensure_cursor_ready(
    *, ping: bool = True, ping_cwd: Path | None = None,
    timeout_sec: float | None = None, retries: int | None = None
) -> CursorHealthReport:
    """Probe and raise if Cursor is not reachable.

    Args:
        ping: Whether to run live ping check
        ping_cwd: Working directory for ping
        timeout_sec: Preflight ping timeout (default: CURSOR_PREFLIGHT_PING_TIMEOUT_SEC or 90s)
        retries: Number of preflight ping attempts (default: CURSOR_PREFLIGHT_PING_RETRIES or 2)
    """
    timeout = timeout_sec if timeout_sec is not None else _preflight_ping_timeout()
    retry_count = retries if retries is not None else _preflight_ping_retries()
    
    last_error = ""
    for attempt in range(1, retry_count + 1):
        report = probe_cursor_stack(run_ping=ping, ping_cwd=ping_cwd, ping_timeout_sec=timeout)
        if report.ok:
            return report
        
        # Classify error for better messaging
        last_error = report.detail
        if not report.wsl_ok:
            reason = "wsl_unreachable"
        elif not report.api_key_ok:
            reason = "api_key_missing"
        elif not report.agent_ok:
            reason = "agent_binary_missing"
        elif not report.backend_ok:
            reason = "cli_backend_disabled"
        elif not report.ping_ok:
            reason = "cold_start_timeout"
        else:
            reason = "unknown"
        
        # On last attempt, raise with classified reason
        if attempt == retry_count:
            raise PreflightError(
                reason=reason,
                message=f"Cursor stack not ready after {retry_count} attempt(s): {last_error}"
            )
        
        # Backoff and retry
        time.sleep(_preflight_ping_backoff_sec(attempt))
        invalidate_wsl_probe_cache()
    
    # Should not reach here
    raise PreflightError(
        reason="unknown",
        message=f"Cursor stack not ready after {retry_count} attempt(s): {last_error}"
    )


def _cursor_ping(*, cwd: Path, timeout_sec: float | None = None) -> tuple[bool, str]:
    """Minimal agent invocation to verify end-to-end connectivity."""
    cli_mod = _import_daedalus_cli()
    key = os.environ.get("CURSOR_API_KEY", "").strip()
    if not key:
        return False, "no API key"
    try:
        timeout = timeout_sec if timeout_sec is not None else _preflight_ping_timeout()
        status, transcript, rc, _model_id = cli_mod.run_agent_cli(
            "Reply with exactly the word PONG and nothing else.",
            cwd=cwd, api_key=key, timeout_sec=timeout,
        )
        ok = status == "finished" and rc == 0
        return ok, transcript[:300] if transcript else f"rc={rc}"
    except Exception as exc:
        return False, str(exc)


def run_agent_cli_with_retry(
    prompt: str,
    *,
    cwd: Path,
    api_key: str,
    timeout_sec: float | None = None,
    max_retries: int | None = None,
    on_retry: Callable[[int, str], None] | None = None,
    call_label: str = "agent",
) -> tuple[str, str, int, str]:
    """Run agent CLI with exponential backoff and cache invalidation.

    Serialization is enforced inside daedalus cursor_cli.run_agent_cli.
    Returns (status, transcript, rc, model_id).
    """
    cli_mod = _import_daedalus_cli()
    run_agent_cli = cli_mod.run_agent_cli
    CursorCLIError = cli_mod.CursorCLIError

    timeout = timeout_sec if timeout_sec is not None else _spawn_timeout()
    retries = max_retries if max_retries is not None else _max_retries()
    last_exc = "unknown error"
    last_transcript = ""
    last_model_id = "auto"

    for attempt in range(1, retries + 1):
        os.environ["_CURSOR_LAST_ATTEMPTS"] = str(attempt)
        os.environ["_CURSOR_CALL_LABEL"] = f"{call_label}:attempt{attempt}"
        if attempt > 1:
            invalidate_wsl_probe_cache()
            _try_wsl_recover_on_stall()
            time.sleep(_retry_backoff_sec(attempt - 1))
            try:
                ensure_cursor_ready(ping=False)
            except CursorConnectivityError as exc:
                last_exc = str(exc)

        try:
            status, transcript, rc, model_id = run_agent_cli(
                prompt, cwd=cwd, api_key=api_key, timeout_sec=timeout,
            )
            last_transcript = transcript
            last_model_id = model_id
            if status == "finished" and rc == 0:
                os.environ["_CURSOR_LAST_ATTEMPTS"] = str(attempt)
                return status, transcript, rc, model_id
            last_exc = transcript[:500] if transcript else f"agent rc={rc}"
            if on_retry:
                on_retry(attempt, last_exc)
        except CursorCLIError as exc:
            last_exc = str(exc)
            msg = str(exc).lower()
            if "stall" in msg or "timed out" in msg:
                _try_wsl_recover_on_stall()
            if not exc.is_retryable:
                raise
            if on_retry:
                on_retry(attempt, last_exc)

    raise CursorConnectivityError(
        f"Cursor agent failed after {retries} attempt(s): {last_exc}; "
        f"transcript={last_transcript[:300]!r}")


def _null_context():
    from contextlib import nullcontext
    return nullcontext()


def _try_wsl_recover_on_stall() -> bool:
    """Best-effort WSL restart after agent stall/timeout."""
    if os.environ.get("HERMES_WSL_AUTO_RECOVER", "1") != "1":
        return False
    try:
        from hermes_live_stack import _try_wsl_recover
        return _try_wsl_recover()
    except ImportError:
        return False
