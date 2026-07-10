#!/usr/bin/env python3
"""Append one stress-campaign run result to JSON ledger."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", required=True)
    parser.add_argument("--seed", required=True)
    parser.add_argument("--rc", type=int, required=True)
    parser.add_argument("--log", required=True)
    parser.add_argument("--results", required=True)
    args = parser.parse_args()

    log_path = Path(args.log)
    log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
    greens = len(re.findall(r"Step S\d+ green", log))
    t09_cursor = len(re.findall(r"T09 generation OK via cursor", log))
    halts = re.findall(r"\[HALT\] (.+)$", log, re.M)
    complete = "PROJECT COMPLETE" in log

    state_path = Path(args.results).resolve().parents[1] / "pipeline_state.json"
    steps_green = 0
    step_total = 0
    if state_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        plan = state.get("master_plan") or []
        step_total = len(plan)
        steps_green = sum(1 for s in plan if s.get("status") == "green")

    entry = {
        "slug": args.slug,
        "seed": args.seed,
        "exit_code": args.rc,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "project_complete": complete,
        "green_commits_log": greens,
        "steps_green": steps_green,
        "step_total": step_total,
        "t09_cursor_ok": t09_cursor,
        "halt": halts[-1] if halts else None,
        "log_path": str(log_path),
    }

    results_path = Path(args.results)
    rows: list = []
    if results_path.is_file():
        try:
            rows = json.loads(results_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            rows = []
    rows.append(entry)
    results_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"[record] {args.slug} rc={args.rc} green={steps_green}/{step_total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
