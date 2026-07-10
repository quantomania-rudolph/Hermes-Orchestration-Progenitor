#!/usr/bin/env python3
"""Summarize stress campaign results and architecture coverage checks."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

LOOP = Path(__file__).resolve().parents[1]
HERMES_ROOT = LOOP.parent

# Tools that must appear in at least one successful run log (§02 phase path)
REQUIRED_MARKERS = [
    ("P0", r"\[P0\]"),
    ("P1", r"\[P1\]"),
    ("P2", r"\[P2\]"),
    ("P3", r"\[P3\]"),
    ("P4", r"\[P4\]"),
    ("P5", r"\[P5\]"),
    ("T09_cursor", r"T09 generation OK via cursor"),
    ("T14_gauntlet", r"Gauntlet|gauntlet"),
    ("final_review", r"final_review|PROJECT COMPLETE"),
]
FORBIDDEN_MARKERS = [
    ("T24_meta", r"T24|tool_synthesizer\.synthesize"),
    ("Qwen_fallback", r"delegating to Hermes/Qwen"),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--results",
        default=str(LOOP / "state" / "stress_campaign_results.json"),
    )
    args = parser.parse_args()
    path = Path(args.results)
    print("=== verify_stress_campaign ===")
    if not path.is_file():
        print(f"[FAIL] missing {path}")
        return 1

    rows = json.loads(path.read_text(encoding="utf-8"))
    failures: list[str] = []
    print(f"[INFO] runs recorded: {len(rows)}")

    for row in rows:
        slug = row.get("slug", "?")
        rc = row.get("exit_code", 99)
        green = row.get("steps_green", 0)
        total = row.get("step_total", 0)
        status = "PASS" if rc == 0 and row.get("project_complete") else "FAIL"
        print(f"  [{status}] {slug}: exit={rc} steps={green}/{total} t09={row.get('t09_cursor_ok')}")
        if row.get("halt"):
            print(f"         halt: {row['halt'][:120]}")
        if rc != 0 or not row.get("project_complete"):
            failures.append(f"{slug} did not complete cleanly")

        log_path = Path(row.get("log_path", ""))
        if log_path.is_file():
            log = log_path.read_text(encoding="utf-8", errors="replace")
            for name, pat in FORBIDDEN_MARKERS:
                if re.search(pat, log, re.I):
                    failures.append(f"{slug}: forbidden marker {name}")

    # Cross-run architecture: at least one run must hit full phase path
    all_logs = ""
    for row in rows:
        lp = Path(row.get("log_path", ""))
        if lp.is_file():
            all_logs += lp.read_text(encoding="utf-8", errors="replace") + "\n"

    for name, pat in REQUIRED_MARKERS:
        if not re.search(pat, all_logs):
            failures.append(f"campaign never saw {name} in any log")

    if failures:
        print("[FAIL] stress campaign verification:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("[OK] stress campaign verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
