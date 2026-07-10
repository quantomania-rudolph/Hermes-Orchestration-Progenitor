#!/usr/bin/env python3
"""Audit live LSTM+Optuna Cursor run: greens, artifacts, pytest, PnL."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parents[1]
HERMES_ROOT = LOOP_DIR.parent
LOG_PATH = LOOP_DIR / "state" / "live_lstm_cursor.log"
STATE_PATH = LOOP_DIR / "pipeline_state.json"
OUT_DIR = HERMES_ROOT / "generated" / "lstm_optuna_vault_trader"
STEP_COUNT = 9


def main() -> int:
    print("=== verify_lstm_live_cursor ===")
    failures: list[str] = []

    log = ""
    if LOG_PATH.is_file():
        log = LOG_PATH.read_text(encoding="utf-8", errors="replace")
        print(f"[OK] log loaded ({len(log)} chars)")
    else:
        failures.append(f"missing log: {LOG_PATH}")

    state: dict | None = None
    if STATE_PATH.is_file():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))

    cursor_hits = len(re.findall(r"T09 generation OK via cursor", log))
    cli_hits = len(re.findall(r"runtime=cli", log))
    qwen_hits = len(re.findall(r"delegating to Hermes/Qwen", log, re.I))
    t24_hits = len(re.findall(r"T24|tool_synthesizer|synthesize\(", log, re.I))
    greens_log = len(re.findall(r"Step S\d+ green", log))
    green_journal = 0
    if state:
        green_journal = sum(
            1 for e in state.get("journal", []) if e.get("transition_type") == "GREEN_COMMIT"
        )

    print(f"[INFO] T09 cursor (log): {cursor_hits} | CLI markers: {cli_hits}")
    print(f"[INFO] Qwen fallbacks: {qwen_hits} | T24/meta-tool hits: {t24_hits}")
    print(f"[INFO] Green commits log={greens_log} journal={green_journal}")

    if t24_hits:
        failures.append(f"T24/meta-tool fired {t24_hits}x — should stay on normal path")
    if qwen_hits:
        failures.append(f"Qwen fallback fired {qwen_hits}x")
    if green_journal < STEP_COUNT and greens_log < STEP_COUNT:
        failures.append(
            f"expected {STEP_COUNT} green commits, log={greens_log} journal={green_journal}"
        )

    done = "PROJECT COMPLETE" in log
    if state and (state.get("runtime") or {}).get("current_phase") == "DONE":
        done = True
    if not done:
        failures.append("session did not reach PROJECT COMPLETE / DONE")

    if state:
        runtime = state.get("runtime") or {}
        if runtime.get("output_slug") != "lstm_optuna_vault_trader":
            failures.append(f"output_slug={runtime.get('output_slug')}")
        for step in state.get("master_plan", []):
            sid = step.get("step_id", "?")
            if step.get("status") != "green":
                failures.append(f"{sid} status={step.get('status')}")
            else:
                print(f"[OK] {sid} green")

    required = [
        OUT_DIR / "config.py",
        OUT_DIR / "data_loader.py",
        OUT_DIR / "signals.py",
        OUT_DIR / "dataset.py",
        OUT_DIR / "nn_model.py",
        OUT_DIR / "partial_forgetting.py",
        OUT_DIR / "purged_kfold.py",
        OUT_DIR / "optuna_tuner.py",
        OUT_DIR / "trading_loop.py",
        OUT_DIR / "portfolio.py",
        OUT_DIR / "backtest_pnl.py",
        OUT_DIR / "run_pipeline.py",
        OUT_DIR / "tests" / "test_lstm_pipeline.py",
        OUT_DIR / "reports" / "pnl_report.json",
        OUT_DIR / "reports" / "pnl_report.md",
        OUT_DIR / "reports" / "model_card.md",
    ]
    for path in required:
        rel = path.relative_to(HERMES_ROOT)
        if not path.is_file():
            failures.append(f"missing: {rel}")
        else:
            print(f"[OK] {rel}")

    stray_prefixes = ("_run_", "_stdlib_", "scratch_")
    if OUT_DIR.is_dir():
        for py in OUT_DIR.rglob("*.py"):
            if any(py.name.startswith(p) for p in stray_prefixes):
                failures.append(f"scratch file: {py.relative_to(HERMES_ROOT)}")

    pnl_path = OUT_DIR / "reports" / "pnl_report.json"
    if pnl_path.is_file():
        try:
            pnl = json.loads(pnl_path.read_text(encoding="utf-8"))
            if not pnl.get("finite_pnl"):
                failures.append("pnl_report.json finite_pnl is false")
            if int(pnl.get("oos_bars", 0)) <= 0:
                failures.append("pnl_report.json oos_bars <= 0")
            else:
                print(f"[OK] PnL oos_bars={pnl.get('oos_bars')} total_pnl={pnl.get('total_pnl')}")
        except (json.JSONDecodeError, TypeError) as exc:
            failures.append(f"pnl_report.json invalid: {exc}")

    test_file = OUT_DIR / "tests" / "test_lstm_pipeline.py"
    if test_file.is_file():
        py = Path(sys.executable)
        venv_py = HERMES_ROOT / ".venv-wsl" / "bin" / "python"
        try:
            if venv_py.is_file():
                py = venv_py
        except OSError:
            pass
        proc = subprocess.run(
            [str(py), "-m", "pytest", str(test_file), "-q", "--tb=short"],
            cwd=str(OUT_DIR),
            capture_output=True,
            text=True,
            timeout=180,
            env={**dict(**{"HERMES_RESEARCH_SMOKE": "1"}), **__import__("os").environ},
        )
        if proc.returncode != 0:
            failures.append(f"pytest failed:\n{proc.stdout[-2000:]}\n{proc.stderr[-1000:]}")
        else:
            print("[OK] pytest passed")

    if failures:
        print("[FAIL] LSTM live audit:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("[OK] LSTM live Cursor run audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
