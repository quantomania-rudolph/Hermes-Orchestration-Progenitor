#!/usr/bin/env python3
"""Audit a live Cursor-first run: tool firing, fallbacks, green commits, artifacts."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parents[1]
HERMES_ROOT = LOOP_DIR.parent
LOG_PATH = LOOP_DIR / "state" / "live_lr_cursor.log"
STATE_PATH = LOOP_DIR / "pipeline_state.json"
OUT_DIR = HERMES_ROOT / "generated" / "vault_lr_strategy"


def main() -> int:
    print("=== verify_live_cursor_audit ===")
    failures: list[str] = []

    if not LOG_PATH.is_file():
        failures.append(f"missing log: {LOG_PATH}")
        log = ""
    else:
        log = LOG_PATH.read_text(encoding="utf-8", errors="replace")
        print(f"[OK] log loaded ({len(log)} chars)")

    state: dict | None = None
    if STATE_PATH.is_file():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))

    cursor_hits = len(re.findall(r"T09 generation OK via cursor", log))
    cli_hits = len(re.findall(r"runtime=cli", log))
    qwen_hits = len(re.findall(r"delegating to Hermes/Qwen", log, re.I))
    t10_skips = len(re.findall(r"T10 review skipped", log))
    greens_log = len(re.findall(r"Step S\d+ green", log))
    green_journal = 0
    if state:
        green_journal = sum(
            1 for e in state.get("journal", []) if e.get("transition_type") == "GREEN_COMMIT"
        )

    print(f"[INFO] T09 cursor delegates (log): {cursor_hits}")
    print(f"[INFO] T09 CLI runtime markers (log): {cli_hits}")
    print(f"[INFO] T09 qwen fallbacks (log): {qwen_hits}")
    print(f"[INFO] T10 infra skips (log): {t10_skips}")
    print(f"[INFO] P4 green commits (log): {greens_log}")
    print(f"[INFO] P4 green commits (journal): {green_journal}")

    if qwen_hits:
        failures.append(f"Qwen fallback fired {qwen_hits}x — Cursor should be primary")
    cursor_spawns = cursor_hits + cli_hits
    if cursor_spawns < 3 and green_journal < 3:
        failures.append(
            f"expected 3 Cursor T09 spawns (log={cursor_spawns}) or 3 GREEN_COMMIT (journal={green_journal})"
        )
    elif cursor_spawns < 3 and green_journal >= 3:
        print("[WARN] log incomplete (buffered stdout) — journal confirms 3 green commits")
    if greens_log < 3 and green_journal < 3:
        failures.append(f"expected 3 green commits, log={greens_log} journal={green_journal}")

    log_incomplete = len(log) < 500
    for phase in ("[P0]", "[P1]", "[P2]", "[P3]", "[P4]", "[P5]"):
        if phase not in log:
            if not log_incomplete:
                failures.append(f"log missing phase marker {phase}")
        else:
            print(f"[OK] saw {phase}")
    if log_incomplete:
        print("[WARN] live log truncated — using pipeline_state.json journal as source of truth")

    done = "PROJECT COMPLETE" in log
    if state and (state.get("runtime") or {}).get("current_phase") == "DONE":
        done = True
        print("[OK] runtime phase DONE")
    if not done:
        failures.append("session did not reach PROJECT COMPLETE / DONE")

    if state:
        journal = {e.get("transition_type") for e in state.get("journal", [])}
        for expected in ("P0_COMPLETE", "PLAN_MUTATION", "GREEN_COMMIT"):
            if expected not in journal:
                failures.append(f"journal missing {expected}")
            else:
                print(f"[OK] journal has {expected}")
        for step in state.get("master_plan", []):
            if step.get("status") != "green":
                failures.append(f"{step['step_id']} status={step.get('status')}")
            else:
                print(f"[OK] {step['step_id']} green")
        runtime = state.get("runtime") or {}
        if runtime.get("output_slug") != "vault_lr_strategy":
            failures.append(f"output_slug={runtime.get('output_slug')}")
    else:
        print("[WARN] pipeline_state.json wiped or missing — checking artifacts only")

    required = [
        OUT_DIR / "data_loader.py",
        OUT_DIR / "signal_model.py",
        OUT_DIR / "backtest_pnl.py",
        OUT_DIR / "tests" / "test_backtest_pnl.py",
        OUT_DIR / "reports" / "pnl_report.json",
        OUT_DIR / "reports" / "pnl_report.md",
    ]
    for path in required:
        if not path.is_file():
            failures.append(f"missing artifact: {path.relative_to(HERMES_ROOT)}")
        else:
            print(f"[OK] {path.relative_to(HERMES_ROOT)}")

    if OUT_DIR.is_dir():
        text = ""
        for py in OUT_DIR.rglob("*.py"):
            try:
                text += py.read_text(encoding="utf-8", errors="replace").lower()
            except OSError:
                pass
        leakage_markers = ("shift(", "walk", "leakage", "oos", "out-of-sample", "out_of_sample")
        if not any(m in text for m in leakage_markers):
            failures.append("LR strategy files lack leakage-control markers")

    if failures:
        print("[FAIL] Live cursor audit:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("[OK] Live Cursor-first LR run audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
