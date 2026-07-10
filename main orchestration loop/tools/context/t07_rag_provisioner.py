"""T07 — Local RAG / Context Provisioner (HYBRID)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.common import ToolResult
from tools.context.index_bridge import IndexBridge

REFERENCE_DOC_GLOBS = (
    "01_HERMES_*.md",
    "02_HERMES_*.md",
    "03_HERMES_*.md",
    "vault_equity*.ipynb",
    "START_HERE.txt",
)


@dataclass
class RAGQueryInput:
    query: str
    top_k: int = 5
    phase: str = "P0"


class RAGProvisioner:
    """Vector search over docs/schemas + codebase via IndexBridge."""

    def __init__(self, bridge: IndexBridge, docs_dir: Path, hermes_root: Path | None = None) -> None:
        self.bridge = bridge
        self.docs_dir = docs_dir
        self.hermes_root = hermes_root or bridge.hermes_root

    def build_step_query(self, step: dict[str, Any]) -> str:
        title = step.get("title", "")
        intent = step.get("intent", "")
        targets = " ".join(step.get("target_files", []))
        return (
            f"implement {title} {intent} {targets} "
            "vault_equity FMP PostgreSQL equity_bars RSI MACD backtest"
        ).strip()

    def run(self, inp: RAGQueryInput) -> ToolResult:
        if not inp.query.strip():
            return ToolResult(False, {}, "Empty RAG query")

        context = self.bridge.query(inp.query, top_k=inp.top_k)
        if context.startswith("RAG error"):
            return ToolResult(False, {"marker": "no-context"}, context)

        codebase_hits = len(re.findall(r"^\[\d+\] sim=", context, re.MULTILINE))
        doc_snippets = self._scan_reference_docs(inp.query)
        return ToolResult(
            True,
            {
                "codebase_context": context,
                "doc_snippets": doc_snippets,
                "codebase_hits": codebase_hits,
                "index_consistent": "index_consistent=True" in context,
            },
            "RAG context provisioned",
        )

    def _scan_reference_docs(self, query: str) -> list[str]:
        tokens = {t for t in query.lower().split() if len(t) > 3}
        hits: list[str] = []

        search_roots = [self.docs_dir, self.hermes_root]
        seen: set[str] = set()
        for root in search_roots:
            if not root.is_dir():
                continue
            for pattern in REFERENCE_DOC_GLOBS:
                for path in root.glob(pattern):
                    key = str(path.resolve())
                    if key in seen or not path.is_file():
                        continue
                    seen.add(key)
                    try:
                        text = path.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        continue
                    lower = text.lower()
                    score = sum(1 for t in tokens if t in lower)
                    if score >= 2 or path.name.lower().startswith("vault_equity"):
                        try:
                            rel = path.relative_to(self.hermes_root)
                        except ValueError:
                            rel = path.name
                        hits.append(f"{rel}: {text[:800]}")
                    if len(hits) >= 5:
                        return hits

        # Fallback: scan loop docs dir by token overlap
        if self.docs_dir.is_dir():
            for path in self.docs_dir.rglob("*"):
                if not path.is_file() or path.suffix not in {".md", ".json", ".yaml", ".yml"}:
                    continue
                key = str(path.resolve())
                if key in seen:
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                lower = text.lower()
                if any(t in lower for t in tokens):
                    hits.append(f"{path.name}: {text[:500]}")
                if len(hits) >= 5:
                    break
        return hits

    def reindex_after_merge(self) -> ToolResult:
        """P4 post-merge re-index pass (T07 authorized in P4)."""
        try:
            if self.bridge.vectors_path.is_file() and self.bridge.load_chunks():
                report = self.bridge.check_consistency()
                if report.consistent:
                    return ToolResult(
                        True,
                        {"built_at": None, "stats": {}, "consistency": report.details},
                        "Post-merge index already consistent (skipped rebuild)",
                    )
        except (FileNotFoundError, ValueError):
            pass
        build = self.bridge.build_index(full_rebuild=False)
        if not build.ok:
            return ToolResult(False, {}, build.message)
        report = self.bridge.check_consistency()
        return ToolResult(
            report.consistent,
            {
                "built_at": build.built_at,
                "stats": build.stats,
                "consistency": report.details,
            },
            "Post-merge reindex complete" if report.consistent else report.details,
        )

    def initialize_at_genesis(self, *, full_if_missing: bool = True) -> ToolResult:
        """P0 index build — ensures codebase_vectors.json exists before P1."""
        built_at = None
        if self.bridge.vectors_path.is_file():
            try:
                chunks = self.bridge.load_chunks()
                if chunks:
                    report = self.bridge.ensure_consistent(auto_reindex=True)
                    return ToolResult(
                        True,
                        {
                            "vectors_path": str(self.bridge.vectors_path),
                            "built_at": None,
                            "consistency": report.details,
                            "reused_existing": True,
                            "chunk_count": len(chunks),
                        },
                        "Genesis index reused (existing chunks on disk)",
                    )
            except (FileNotFoundError, ValueError):
                pass

        build = self.bridge.build_index(full_rebuild=full_if_missing)
        if not build.ok:
            return ToolResult(False, {}, build.message)
        built_at = build.built_at
        report = self.bridge.ensure_consistent(auto_reindex=True)
        return ToolResult(
            report.consistent or build.ok,
            {
                "vectors_path": str(self.bridge.vectors_path),
                "built_at": built_at,
                "consistency": report.details,
                "chunk_count": build.stats.get("chunks", 0),
            },
            "Genesis index ready",
        )
