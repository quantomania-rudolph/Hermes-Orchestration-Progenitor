#!/usr/bin/env python3
"""Verify RAG returns useful hits (not snapshot noise) for trading queries."""

from __future__ import annotations

import sys
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parents[1]
HERMES_ROOT = LOOP_DIR.parent
sys.path.insert(0, str(LOOP_DIR))
sys.path.insert(0, str(HERMES_ROOT))

from config.loop_config import BUILD_INDEX_SCRIPT, DOCS_DIR, HERMES_ROOT, INDEX_CONSISTENCY_LOG, VECTORS_PATH  # noqa: E402
from tools.context.index_bridge import IndexBridge  # noqa: E402
from tools.context.t07_rag_provisioner import RAGProvisioner, RAGQueryInput  # noqa: E402


def main() -> int:
    print("=== verify_rag_quality ===")
    bridge = IndexBridge(
        build_script=BUILD_INDEX_SCRIPT,
        vectors_path=VECTORS_PATH,
        hermes_root=HERMES_ROOT,
        consistency_log=INDEX_CONSISTENCY_LOG,
    )
    rag = RAGProvisioner(bridge, DOCS_DIR, HERMES_ROOT)

    query = (
        "vault_equity FMP stable API PostgreSQL equity_bars 5min "
        "RSI MACD data_loader backtest"
    )
    result = rag.run(RAGQueryInput(query=query, top_k=5, phase="P2"))
    if not result.ok:
        print(f"[FAIL] RAG query failed: {result.message}")
        return 1

    ctx = result.data.get("codebase_context", "")
    hits = result.data.get("codebase_hits", 0)
    docs = result.data.get("doc_snippets", [])
    print(f"[INFO] codebase_hits={hits} doc_snippets={len(docs)}")

    if hits < 1:
        print("[FAIL] No codebase vector hits")
        return 1

    if "file_snapshots" in ctx.split("===")[0] if "===" in ctx else ctx[:500]:
        # top section should not be dominated by snapshots after filter
        top_files = ctx[:3000]
        if top_files.count("file_snapshots") > top_files.count("vault_equity"):
            print("[FAIL] RAG still dominated by file_snapshots")
            return 1

    useful = any(
        kw in ctx.lower()
        for kw in ("vault_equity", "fmp", "equity_bars", "postgresql", "data_loader")
    )
    if not useful:
        print("[FAIL] Top RAG hits lack trading/data keywords")
        return 1
    print("[OK] RAG returns relevant trading/data context")

    if not docs:
        print("[WARN] No reference doc snippets — check vault_equity*.ipynb at repo root")
    else:
        has_vault = any("vault_equity" in d.lower() for d in docs)
        if has_vault:
            print("[OK] vault_equity notebook included in doc snippets")
        else:
            print(f"[OK] {len(docs)} reference doc snippet(s) attached")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
