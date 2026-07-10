#!/usr/bin/env python3
"""Run HERMES sequentially on quant pipeline seeds, then optional DAEDALUS RSI pass."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parent
HERMES_ROOT = LOOP_DIR.parent
DAEDALUS_ROOT = HERMES_ROOT / "daedalus"

SEEDS = [
    "pipeline_state.quant_attention_trader.seed.json",
    "pipeline_state.leakage_audit_pipeline.seed.json",
    "pipeline_state.factor_momentum_portfolio.seed.json",
    "pipeline_state.vol_targeting_allocator.seed.json",
    "pipeline_state.cross_asset_risk_monitor.seed.json",
]


def run_hermes(seed_name: str, *, dry_run: bool = False) -> dict:
    seed = LOOP_DIR / seed_name
    if not seed.is_file():
        return {"ok": False, "seed": seed_name, "error": "seed missing"}
    cmd = [
        sys.executable, str(LOOP_DIR / "orchestrator" / "main.py"),
        "--seed", str(seed.resolve()),
        "--repo", str(HERMES_ROOT),
    ]
    if dry_run:
        cmd.append("--dry-run")
    t0 = time.monotonic()
    proc = subprocess.run(cmd, cwd=str(LOOP_DIR), capture_output=True, text=True)
    elapsed = time.monotonic() - t0
    slug = json.loads(seed.read_text(encoding="utf-8"))["genesis_baseline"]["output_slug"]
    out_dir = HERMES_ROOT / "generated" / slug
    return {
        "ok": proc.returncode == 0,
        "seed": seed_name,
        "slug": slug,
        "elapsed_sec": elapsed,
        "generated_exists": out_dir.is_dir(),
        "stdout_tail": proc.stdout[-1500:],
        "stderr_tail": proc.stderr[-800:],
    }


def run_daedalus(slug: str) -> dict:
    script = DAEDALUS_ROOT / "verification" / "live" / "run_all_generated_campaigns.py"
    if not script.is_file():
        return {"ok": False, "error": "daedalus campaign script missing"}
    proc = subprocess.run(
        [sys.executable, str(script), "--target", slug, "--epochs", "3", "--rounds", "4"],
        cwd=str(DAEDALUS_ROOT),
        capture_output=True,
        text=True,
        timeout=900,
    )
    return {
        "ok": proc.returncode == 0,
        "slug": slug,
        "stdout_tail": proc.stdout[-1000:],
        "stderr_tail": proc.stderr[-500:],
    }


def main() -> int:
    from hermes_live_stack import configure_intel_arc_defaults, enforce_hermes_live_stack

    configure_intel_arc_defaults()
    enforce_hermes_live_stack()

    ap = argparse.ArgumentParser()
    ap.add_argument("--hermes-only", action="store_true")
    ap.add_argument("--daedalus-only", action="store_true")
    ap.add_argument("--seed", nargs="*", default=SEEDS)
    ap.add_argument("--report", type=Path, default=LOOP_DIR / "quant_batch_report.json")
    args = ap.parse_args()

    results: list[dict] = []
    for seed_name in args.seed:
        print(f"\n>>> HERMES {seed_name}")
        if not args.daedalus_only:
            hres = run_hermes(seed_name, dry_run=False)
            print(f"  hermes ok={hres['ok']} slug={hres.get('slug')} ({hres.get('elapsed_sec', 0):.0f}s)")
            results.append({"phase": "hermes", **hres})
            if not hres.get("ok"):
                continue
        if not args.hermes_only:
            slug = json.loads((LOOP_DIR / seed_name).read_text(encoding="utf-8"))["genesis_baseline"]["output_slug"]
            print(f"  >>> DAEDALUS {slug}")
            dres = run_daedalus(slug)
            print(f"  daedalus ok={dres['ok']}")
            results.append({"phase": "daedalus", **dres})

    args.report.write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")
    ok = all(r.get("ok") for r in results) if results else False
    print(f"\nReport: {args.report}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
