"""Capture a machine-readable snapshot of a generated output tree for evolution logging.

Usage (from repo root):
    python "main orchestration loop/tools/meta/t_evolution_log_snapshot.py" pairs_regime_ukf_trader
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    # .../main orchestration loop/tools/meta/t_evolution_log_snapshot.py
    return here.parents[3]


def _sha16(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _line_count(path: Path) -> int:
    try:
        return sum(1 for _ in path.open("r", encoding="utf-8", errors="replace"))
    except OSError:
        return 0


def _load_pipeline_state(loop_root: Path) -> dict:
    state_path = loop_root / "pipeline_state.json"
    if not state_path.is_file():
        return {}
    return json.loads(state_path.read_text(encoding="utf-8"))


def snapshot(slug: str) -> dict:
    root = _repo_root()
    loop_root = root / "main orchestration loop"
    out_root = root / "generated" / slug
    state = _load_pipeline_state(loop_root)

    skip = {".pytest_cache", "__pycache__"}
    inventory: dict[str, dict] = {}
    prod_lines = 0
    test_lines = 0

    for path in sorted(out_root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in skip for part in path.parts):
            continue
        rel = path.relative_to(out_root).as_posix()
        lines = _line_count(path)
        entry = {
            "lines": lines,
            "sha16": _sha16(path),
            "bytes": path.stat().st_size,
        }
        inventory[rel] = entry
        if rel.endswith(".py"):
            if rel.startswith("tests/"):
                test_lines += lines
            elif not rel.startswith("_"):
                prod_lines += lines

    plan_progress = {}
    for step in state.get("master_plan", []):
        plan_progress[step.get("step_id", "?")] = step.get("status", "unknown")

    runtime = state.get("runtime", {})
    if runtime.get("output_slug") != slug and runtime.get("output_root", "").replace("\\", "/").endswith(slug):
        pass  # tolerate path-only match

    return {
        "slug": slug,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "captured_by": "t_evolution_log_snapshot",
        "pipeline": {
            "current_phase": runtime.get("current_phase"),
            "active_step_id": runtime.get("active_step_id"),
            "horizon_window": state.get("horizon", {}).get("window"),
            "budget_usd_used": state.get("budget", {}).get("usd_used"),
            "budget_usd_cap": state.get("budget", {}).get("usd_cap"),
            "strike_ledger": state.get("strike_ledger", {}),
        },
        "plan_progress": plan_progress,
        "file_inventory": inventory,
        "totals": {
            "production_py_lines": prod_lines,
            "test_py_lines": test_lines,
            "files_on_disk": len(inventory),
            "completion_pct_by_steps": round(
                100 * sum(1 for s in plan_progress.values() if s == "green") / max(len(plan_progress), 1)
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("slug", help="output slug under generated/")
    parser.add_argument(
        "--write",
        action="store_true",
        help="write JSON next to evolution log markdown",
    )
    args = parser.parse_args()

    data = snapshot(args.slug)
    text = json.dumps(data, indent=2)
    print(text)

    if args.write:
        out = (
            _repo_root()
            / "main orchestration loop"
            / "state"
            / "evolution_logs"
            / f"{args.slug}_snapshot.json"
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {out}", flush=True)


if __name__ == "__main__":
    main()
