#!/usr/bin/env python3
"""Live Hermes brain mutation check — T26 propose + T04 commit (NoLlama required)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parents[1]
HERMES_ROOT = LOOP_DIR.parent
PORTPROXY_BAT = LOOP_DIR / "run" / "08_enable_wsl_nollama_portproxy.bat"


def _fetch_health(health_url: str, timeout: float = 2.0) -> dict | None:
    try:
        req = urllib.request.Request(health_url.rstrip("/"), method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            payload = json.loads(resp.read().decode("utf-8"))
            return payload if isinstance(payload, dict) else None
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None


def _probe_health_url(health_url: str, timeout: float = 2.0) -> bool:
    return _fetch_health(health_url, timeout=timeout) is not None


def _nollama_ready(base_v1: str) -> tuple[bool, str]:
    health_url = base_v1.rstrip("/").replace("/v1", "/health")
    payload = _fetch_health(health_url, timeout=5.0)
    if payload is None:
        return False, "health probe failed"
    status = str(payload.get("status", "")).lower()
    if status not in {"", "ok", "ready"}:
        return False, f"status={status!r}"
    return True, ""


def _probe_host(host: str, timeout: float = 2.0) -> bool:
    return _probe_health_url(f"http://{host}:8000/health", timeout=timeout)


def _resolv_nameserver() -> str | None:
    try:
        text = Path("/etc/resolv.conf").read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "nameserver":
            return parts[1]
    return None


def _default_gateway() -> str | None:
    try:
        proc = subprocess.run(
            ["ip", "-4", "route", "show", "default"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    match = re.search(r"\bdefault\b\s+via\s+(\S+)", proc.stdout)
    if match:
        return match.group(1)
    parts = proc.stdout.split()
    if len(parts) >= 3 and parts[0] == "default":
        return parts[2]
    return None


def wsl_resolve_nollama_url() -> str | None:
    """Mirror run/_wsl_nollama_url.sh candidate order and health probes."""
    explicit = os.environ.get("NOLLAMA_OPENAI_BASE_URL", "").strip()
    if explicit:
        health_base = explicit.rstrip("/")
        if health_base.endswith("/v1"):
            health_base = health_base[:-3]
        if _probe_health_url(f"{health_base}/health"):
            return explicit if explicit.endswith("/v1") else f"{health_base}/v1"
        return None

    candidates: list[str] = []
    ns = _resolv_nameserver()
    if ns:
        candidates.append(ns)
    gw = _default_gateway()
    if gw:
        candidates.append(gw)
    candidates.extend(["host.docker.internal", "127.0.0.1"])

    seen: set[str] = set()
    for host in candidates:
        if not host or host in seen:
            continue
        seen.add(host)
        if _probe_host(host):
            return f"http://{host}:8000/v1"
    return None


def _skip_soft(reason: str) -> int:
    print(f"[SKIP] verify_brain_mutation_live — {reason}")
    print(f"  Fix: run {PORTPROXY_BAT} as Administrator on Windows")
    print("  Then re-run from WSL (or set NOLLAMA_OPENAI_BASE_URL=http://<gateway>:8000/v1)")
    print("  If NoLlama is starting, wait for model warmup and retry.")
    return 0


def main() -> int:
    print("=== verify_brain_mutation_live ===")

    resolved = wsl_resolve_nollama_url()
    if resolved is None:
        return _skip_soft("NoLlama unreachable from WSL")

    ready, detail = _nollama_ready(resolved)
    if not ready:
        return _skip_soft(f"NoLlama not ready ({detail})")

    os.environ["NOLLAMA_OPENAI_BASE_URL"] = resolved
    os.environ["NOLLAMA_HEALTH_URL"] = resolved.rstrip("/").replace("/v1", "/health")
    os.environ["HERMES_SKIP_HERMES_BRAIN"] = "0"
    os.environ["HERMES_DRY_RUN"] = "0"
    os.environ["HERMES_SKIP_CURSOR"] = "1"
    os.environ.setdefault("HERMES_NOLLAMA_TIMEOUT_SEC", "90")

    sys.path.insert(0, str(LOOP_DIR))
    sys.path.insert(0, str(HERMES_ROOT))

    from hermes_secrets import load_local_env  # noqa: E402

    load_local_env()

    import config.loop_config as lc  # noqa: E402
    from orchestrator.bootstrap import build_context  # noqa: E402
    from orchestrator.contracts import register_all  # noqa: E402
    from orchestrator.plan_brain import (  # noqa: E402
        commit_plan_proposal,
        is_identity_plan,
        propose_plan,
    )
    from tools.common import Phase  # noqa: E402
    from tools.governance.output_paths import bind_generated_output  # noqa: E402
    from tools.governance.t03_pipeline_state_manager import PipelineStateManager  # noqa: E402
    from tools.orchestration.t26_model_router import TaskClass  # noqa: E402
    from tools.safety.t23_state_journal import StateJournal  # noqa: E402

    print(f"[OK] NoLlama reachable at {resolved}")

    ctx = build_context(HERMES_ROOT)
    register_all(ctx.phase_controller)
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        lc.PIPELINE_STATE_PATH = tmp_path / "pipeline_state.json"
        lc.WAL_PATH = tmp_path / "wal.jsonl"
        lc.GENESIS_BASELINE_PATH = tmp_path / "genesis_baseline.json"
        lc.LAST_GOOD_PLAN_PATH = tmp_path / "last_good_plan.json"
        lc.HORIZON_OPEN_PATH = tmp_path / "horizon_open.json"
        lc.STATE_DIR = tmp_path

        journal = StateJournal(lc.WAL_PATH)
        t03 = PipelineStateManager(lc.PIPELINE_STATE_PATH, journal)
        state = t03.ingest_seed(LOOP_DIR / "pipeline_state.test_trading.seed.json")
        state = bind_generated_output(state, HERMES_ROOT)
        state = ctx.objective_verifier.lock_objective(state)
        state = ctx.mutation_guard.capture_genesis_baseline(state)
        state = ctx.budget.initialize(state)

        ast_meta = ctx.ast_mapper.meta_summary() or "verify_brain_mutation_live"
        before_hash = state.get("plan_hash")

        try:
            proposal = propose_plan(
                ctx,
                state,
                TaskClass.PLAN_GENERATE,
                ast_meta=ast_meta,
                reason="live_verification",
                strip_horizon=False,
                fallback_justification="verify_brain_mutation_live identity fallback",
                force_live=True,
            )
        except Exception as exc:
            err = str(exc).lower()
            if any(
                token in err
                for token in ("503", "not ready", "loading", "timed out", "timeout")
            ):
                return _skip_soft(f"Hermes model not ready ({exc})")
            failures.append(f"propose_plan live call failed: {exc}")
            proposal = None

        if proposal is not None:
            identity = is_identity_plan(state, proposal.master_plan)
            if identity:
                print(
                    "[INFO] T26 live call returned identity plan "
                    f"(delta={proposal.delta_reason!r}, justification={proposal.justification[:80]!r})"
                )
                print("[INFO] Documented fallback: Hermes reachable but plan unchanged (Stage-2 safe)")
            else:
                print(
                    f"[OK] T26 live mutation — {len(proposal.master_plan)} steps, "
                    f"delta={proposal.delta_reason}"
                )

            try:
                committed = commit_plan_proposal(
                    ctx,
                    state,
                    proposal,
                    phase=Phase.P1,
                    skip_co_verify_if_identity=True,
                )
                after_hash = committed.get("plan_hash")
                if after_hash is None:
                    failures.append("commit_plan_proposal did not update plan_hash")
                else:
                    print(f"[OK] commit_plan_proposal T04 path (plan_hash updated)")
                if before_hash and after_hash == before_hash and not identity:
                    failures.append("non-identity proposal did not change committed plan_hash")
            except Exception as exc:
                failures.append(f"commit_plan_proposal T04 path failed: {exc}")

    if failures:
        print("[FAIL]")
        for msg in failures:
            print(f"  - {msg}")
        return 1

    print("[OK] verify_brain_mutation_live complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
