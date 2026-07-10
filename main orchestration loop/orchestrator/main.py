#!/usr/bin/env python3
"""Entry point for the HERMES main orchestration loop."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parents[1]
HERMES_ROOT = LOOP_DIR.parent
if str(HERMES_ROOT) not in sys.path:
    sys.path.insert(0, str(HERMES_ROOT))
if str(LOOP_DIR) not in sys.path:
    sys.path.insert(0, str(LOOP_DIR))

from hermes_secrets import load_local_env  # noqa: E402

load_local_env()

from config.loop_config import HERMES_ROOT, LOOP_DIR  # noqa: E402
from orchestrator.session import main_entry  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="HERMES main orchestration loop — pipeline_state.json driven autonomous factory."
    )
    parser.add_argument(
        "--seed",
        type=Path,
        default=LOOP_DIR / "pipeline_state.seed.json",
        help="User-seeded pipeline_state JSON (default: pipeline_state.seed.json)",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=HERMES_ROOT,
        help="Repository root for AST/diff/index scope",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from existing pipeline_state.json instead of fresh P0",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Set HERMES_DRY_RUN=1 for stubbed P2/P3 (no Cursor spawns)",
    )
    args = parser.parse_args()

    import os

    if args.dry_run:
        os.environ["HERMES_DRY_RUN"] = "1"
        os.environ.setdefault("HERMES_SKIP_CURSOR", "1")

    return main_entry(args.seed.resolve(), args.repo.resolve(), resume=args.resume)


if __name__ == "__main__":
    raise SystemExit(main())
