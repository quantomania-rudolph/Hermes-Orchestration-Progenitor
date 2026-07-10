#!/usr/bin/env python3
"""Verify T09 Qwen delegation can write target files when Cursor bridge is down."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parents[1]
HERMES_ROOT = LOOP_DIR.parent
sys.path.insert(0, str(LOOP_DIR))
sys.path.insert(0, str(HERMES_ROOT))

from hermes_secrets import load_local_env  # noqa: E402

load_local_env()

from agents.hermes_local_creator import HermesLocalCreator  # noqa: E402
from tools.governance.t01_objective_envelope import ObjectiveEnvelope  # noqa: E402
from tools.governance.t02_objective_hash import ObjectiveHashVerifier  # noqa: E402


def main() -> int:
    print("=== verify_t09_qwen_delegate ===")
    out_dir = HERMES_ROOT / "generated" / "_t09_smoke_test"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    target = "generated/_t09_smoke_test/hello.py"

    seed = json.loads((LOOP_DIR / "pipeline_state.test_trading.seed.json").read_text(encoding="utf-8"))
    state = ObjectiveHashVerifier().lock_objective(seed)
    wrapped = ObjectiveEnvelope(ObjectiveHashVerifier()).wrap(state, "smoke test", "")

    creator = HermesLocalCreator()
    result = creator.run(
        repo_root=HERMES_ROOT,
        wrapped_prompt=wrapped,
        creator_prompt=(
            "Write hello.py containing exactly:\n"
            "def greet() -> str:\n"
            '    return "HERMES_QWEN_OK"\n'
        ),
        target_files=[target],
    )

    path = HERMES_ROOT / target
    if not result.ok or not path.is_file():
        print(f"[FAIL] Qwen delegate did not write file: ok={result.ok}")
        print(result.transcript[:500])
        return 1
    if "HERMES_QWEN_OK" not in path.read_text(encoding="utf-8"):
        print("[FAIL] Generated file missing expected content")
        return 1

    print("[OK] T09 Qwen delegation wrote target file successfully")
    shutil.rmtree(out_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
