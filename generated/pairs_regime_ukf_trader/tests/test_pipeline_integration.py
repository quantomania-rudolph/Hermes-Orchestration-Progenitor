"""End-to-end smoke integration for pairs_regime_ukf_trader."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

_PKG = Path(__file__).resolve().parents[1]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

os.environ["HERMES_RESEARCH_SMOKE"] = "1"

from run_pipeline import SMOKE_TIMEOUT_SEC, run_pipeline, run_with_timeout


def test_smoke_pipeline_completes_under_budget():
    start = time.monotonic()
    metrics = run_with_timeout(lambda: run_pipeline(smoke=True), SMOKE_TIMEOUT_SEC)
    elapsed = time.monotonic() - start
    assert elapsed < SMOKE_TIMEOUT_SEC, f"pipeline took {elapsed:.1f}s (budget {SMOKE_TIMEOUT_SEC}s)"
    assert metrics["oos_bars"] > 0
    assert metrics["finite_pnl"] is True
    assert int(metrics["trade_count"]) > 0
    assert metrics.get("smoke") is True


def test_cli_smoke_flag_runs_full_path_under_budget():
    env = os.environ.copy()
    env["HERMES_RESEARCH_SMOKE"] = "1"
    start = time.monotonic()
    proc = subprocess.run(
        [sys.executable, str(_PKG / "run_pipeline.py"), "--smoke"],
        cwd=str(_PKG),
        capture_output=True,
        text=True,
        timeout=SMOKE_TIMEOUT_SEC,
        check=False,
        env=env,
    )
    elapsed = time.monotonic() - start
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert elapsed < SMOKE_TIMEOUT_SEC, f"CLI smoke took {elapsed:.1f}s (budget {SMOKE_TIMEOUT_SEC}s)"
    summary = json.loads(proc.stdout)
    assert summary.get("smoke") is True
    assert int(summary.get("oos_bars", 0)) > 0
    assert summary.get("finite_pnl") is True
    assert int(summary.get("trade_count", 0)) > 0


def test_reports_and_device_artifact_exist():
    reports = _PKG / "reports"
    run_pipeline(smoke=True)
    for name in (
        "pnl_report.json",
        "regime_timeline.json",
        "pair_audit.json",
        "pnl_report.md",
        "device_report.json",
    ):
        path = reports / name
        assert path.is_file(), f"missing report artifact: {name}"
        if path.suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            assert payload


def test_verify_passes_after_smoke_run():
    from backtest_pnl import verify

    run_pipeline(smoke=True)
    assert verify() is True
