#!/usr/bin/env python3
"""Verify codebase_vectors.json is present and usable for Hermes RAG."""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERMES_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERMES_DIR))

from hermes_config import BUILD_INDEX_SCRIPT, VECTORS_PATH  # noqa: E402


def main() -> int:
    print("=== Verify RAG index ===")
    print(f"Index file: {VECTORS_PATH}")
    print(f"Build script: {BUILD_INDEX_SCRIPT}")
    print()

    if not BUILD_INDEX_SCRIPT.is_file():
        print(f"[FAIL] Missing build script: {BUILD_INDEX_SCRIPT}")
        return 1
    print(f"[OK] build_index.py present")

    if not VECTORS_PATH.is_file():
        print(f"[FAIL] Index not found. Run: scripts\\setup_index\\01_build_index.bat")
        return 1

    try:
        payload = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            chunks = payload.get("chunks", [])
            registry = payload.get("file_mtimes", {})
        elif isinstance(payload, list):
            chunks = payload
            registry = {}
        else:
            print("[FAIL] Unexpected JSON structure")
            return 1

        if not chunks:
            print("[FAIL] Index has zero chunks. Run: scripts\\setup_index\\01_build_index.bat")
            return 1

        has_vector = bool(chunks[0].get("vector"))
        size_mb = VECTORS_PATH.stat().st_size / (1024 * 1024)
        print(f"[OK] chunks={len(chunks)}  files_in_registry={len(registry)}  size={size_mb:.1f} MB")
        if not has_vector:
            print("[WARN] Sample chunk missing vector — index may be incomplete")
            return 1
        print("[OK] Sample chunk has embedding vector")
    except Exception as exc:
        print(f"[FAIL] Could not read index: {exc}")
        return 1

    print("\nRAG index is ready for hermes_orchestrator.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
