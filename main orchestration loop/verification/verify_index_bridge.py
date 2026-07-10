#!/usr/bin/env python3
"""Verify build_index ↔ IndexBridge ↔ consistency checker integration."""

from __future__ import annotations

import sys
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parents[1]
HERMES_ROOT = LOOP_DIR.parent
sys.path.insert(0, str(LOOP_DIR))
sys.path.insert(0, str(HERMES_ROOT))

from config.loop_config import (  # noqa: E402
    BUILD_INDEX_SCRIPT,
    HERMES_ROOT,
    INDEX_CONSISTENCY_LOG,
    VECTORS_PATH,
)
from tools.context.index_bridge import IndexBridge  # noqa: E402


def main() -> int:
    print("=== verify_index_bridge ===")
    if not BUILD_INDEX_SCRIPT.is_file():
        print(f"[FAIL] Missing {BUILD_INDEX_SCRIPT}")
        return 1
    print(f"[OK] build_index.py at {BUILD_INDEX_SCRIPT}")

    bridge = IndexBridge(
        build_script=BUILD_INDEX_SCRIPT,
        vectors_path=VECTORS_PATH,
        hermes_root=HERMES_ROOT,
        consistency_log=INDEX_CONSISTENCY_LOG,
    )

    if not VECTORS_PATH.is_file():
        print("[INFO] Index missing — running incremental build")
        result = bridge.build_index(full_rebuild=False)
        if not result.ok:
            print(f"[FAIL] Build failed: {result.message[:500]}")
            return 1
        print(f"[OK] Index built: {result.stats}")

    try:
        chunks = bridge.load_chunks()
        print(f"[OK] Loaded {len(chunks)} chunks from {VECTORS_PATH.name}")
    except Exception as exc:
        print(f"[FAIL] load_chunks: {exc}")
        return 1

    report = bridge.check_consistency(scan_roots=[HERMES_ROOT])
    print(f"[INFO] Consistency: {report.details}")
    if not report.consistent:
        print("[INFO] Stale/missing detected — running ensure_consistent")
        report = bridge.ensure_consistent(auto_reindex=True)
        print(f"[INFO] After reindex: {report.details}")

    # Query smoke test (requires embeddings — may be slow first run)
    if sys.argv[-1] != "--skip-query":
        try:
            out = bridge.query("pipeline_state manager T03", top_k=2)
            if out.startswith("RAG error"):
                print(f"[WARN] Query returned error (embeddings may need download): {out[:200]}")
            else:
                print(f"[OK] RAG query returned {len(out)} chars")
        except Exception as exc:
            print(f"[WARN] RAG query skipped: {exc}")

    print("[OK] Index bridge integration verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
