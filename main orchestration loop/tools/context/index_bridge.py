"""
Index Bridge — links T07 to parent build_index.py and enforces index consistency.

Addresses the two-index problem:
  1. BUILD INDEX  — scripts/setup_index/build_index.py → codebase_vectors.json
  2. CONSISTENT INDEX — file_mtimes registry must match on-disk reality before RAG queries
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class IndexBuildResult:
    ok: bool
    message: str
    stats: dict[str, int]
    built_at: float | None


@dataclass
class ConsistencyReport:
    consistent: bool
    missing_on_disk: list[str]
    stale_in_index: list[str]
    extra_on_disk: list[str]
    checked_at: float
    details: str


class IndexBridge:
    """Unified interface between the orchestration loop and the parent RAG index."""

    def __init__(
        self,
        *,
        build_script: Path,
        vectors_path: Path,
        hermes_root: Path,
        consistency_log: Path,
    ) -> None:
        self.build_script = build_script
        self.vectors_path = vectors_path
        self.hermes_root = hermes_root
        self.consistency_log = consistency_log

    def build_index(self, *, full_rebuild: bool = False) -> IndexBuildResult:
        if not self.build_script.is_file():
            return IndexBuildResult(
                False,
                f"Build script missing: {self.build_script}",
                {},
                None,
            )
        cmd = [sys.executable, str(self.build_script)]
        if full_rebuild:
            cmd.append("--full")
        # Scope builds to the Hermes project by default — avoids multi-root OOM from
        # VS Code workspace discovery (FILE OF DATA, etc.) during orchestration runs.
        env = os.environ.copy()
        env.setdefault("HERMES_WORKSPACE_ROOTS", str(self.hermes_root))
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,
            cwd=str(self.hermes_root),
            env=env,
        )
        combined = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            return IndexBuildResult(
                False,
                f"build_index failed (exit {proc.returncode}):\n{combined[-4000:]}",
                {},
                None,
            )
        built_at = None
        if self.vectors_path.is_file():
            try:
                payload = json.loads(self.vectors_path.read_text(encoding="utf-8"))
                built_at = float(payload.get("built_at", time.time()))
            except (json.JSONDecodeError, OSError):
                built_at = time.time()
        return IndexBuildResult(
            True,
            "Index build completed",
            self._parse_stats(combined),
            built_at,
        )

    @staticmethod
    def _parse_stats(output: str) -> dict[str, int]:
        stats: dict[str, int] = {}
        for key in ("scanned", "embedded", "reused", "removed", "chunks"):
            for line in output.splitlines():
                if f"{key}=" in line:
                    try:
                        part = line.split(f"{key}=")[1].split()[0]
                        stats[key] = int(part)
                    except (IndexError, ValueError):
                        pass
        return stats

    def load_chunks(self) -> list[dict[str, Any]]:
        if not self.vectors_path.is_file():
            raise FileNotFoundError(
                f"Missing {self.vectors_path.name}. Run build_index first."
            )
        raw = json.loads(self.vectors_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return list(raw.get("chunks", []))
        if isinstance(raw, list):
            return raw
        raise ValueError("Unexpected index JSON shape")

    def check_consistency(
        self,
        *,
        scan_roots: list[Path] | None = None,
    ) -> ConsistencyReport:
        """Verify index file_mtimes registry matches on-disk modification times."""
        checked_at = time.time()
        if not self.vectors_path.is_file():
            return ConsistencyReport(
                False,
                [],
                [],
                [],
                checked_at,
                "Index file does not exist",
            )

        payload = json.loads(self.vectors_path.read_text(encoding="utf-8"))
        registry: dict[str, float] = {}
        if isinstance(payload, dict):
            registry = {k: float(v) for k, v in payload.get("file_mtimes", {}).items()}

        if scan_roots is None:
            scan_roots = [self.hermes_root]

        disk_files: dict[str, float] = {}
        for root in scan_roots:
            if not root.is_dir():
                continue
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [
                    d
                    for d in dirnames
                    if d not in {".git", "node_modules", "__pycache__", ".venv", "venv"}
                ]
                for name in filenames:
                    path = Path(dirpath) / name
                    if path.name == self.vectors_path.name:
                        continue
                    try:
                        rel = str(path.relative_to(root)).replace("\\", "/")
                        disk_files[rel] = os.path.getmtime(path)
                    except (ValueError, OSError):
                        continue

        stale: list[str] = []
        missing: list[str] = []
        for file_key, indexed_mtime in registry.items():
            if file_key not in disk_files:
                missing.append(file_key)
            elif abs(disk_files[file_key] - indexed_mtime) >= 1.0:
                stale.append(file_key)

        extra = [k for k in disk_files if k not in registry]

        consistent = not stale and not missing
        details = (
            f"registry={len(registry)} disk_tracked={len(disk_files)} "
            f"stale={len(stale)} missing={len(missing)} extra={len(extra)}"
        )
        report = ConsistencyReport(
            consistent=consistent,
            missing_on_disk=missing,
            stale_in_index=stale,
            extra_on_disk=extra[:50],
            checked_at=checked_at,
            details=details,
        )
        self._log_consistency(report)
        return report

    def _log_consistency(self, report: ConsistencyReport) -> None:
        self.consistency_log.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "checked_at": report.checked_at,
            "consistent": report.consistent,
            "stale_count": len(report.stale_in_index),
            "missing_count": len(report.missing_on_disk),
            "details": report.details,
        }
        with self.consistency_log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

    def ensure_consistent(self, *, auto_reindex: bool = True) -> ConsistencyReport:
        report = self.check_consistency()
        if report.consistent or not auto_reindex:
            return report
        build = self.build_index(full_rebuild=False)
        if not build.ok:
            report.details += f"; auto_reindex failed: {build.message[:200]}"
            return report
        return self.check_consistency()

    def query(
        self,
        search_query: str,
        *,
        top_k: int = 3,
        embed_fn: Any = None,
    ) -> str:
        if not search_query.strip():
            return "RAG error: empty query"
        report = self.ensure_consistent(auto_reindex=True)
        if not report.consistent:
            return (
                f"RAG warning: index still inconsistent after reindex. {report.details}"
            )
        try:
            chunks = self.load_chunks()
        except (FileNotFoundError, ValueError) as exc:
            return f"RAG error: {exc}"

        if embed_fn is None:
            sys.path.insert(0, str(self.hermes_root))
            from hermes_embeddings import embed_query as embed_fn  # noqa: WPS433

        query_vec = np.asarray(embed_fn(search_query), dtype=np.float32)
        norm = float(np.linalg.norm(query_vec))
        if norm <= 0:
            return "RAG error: zero-norm query embedding"
        query_vec = query_vec / norm

        vectors: list[np.ndarray] = []
        valid: list[dict[str, Any]] = []
        for entry in chunks:
            raw_vec = entry.get("vector")
            if not raw_vec:
                continue
            vec = np.asarray(raw_vec, dtype=np.float32)
            vn = float(np.linalg.norm(vec))
            if vn <= 0:
                continue
            vectors.append(vec / vn)
            valid.append(entry)
        if not vectors:
            return "RAG error: no valid vectors in index"

        matrix = np.vstack(vectors)
        scores = matrix @ query_vec
        k = min(top_k, len(scores))
        top_idx = np.argpartition(-scores, k - 1)[:k]
        top_idx = top_idx[np.argsort(-scores[top_idx])]

        lines = [f"=== LOCAL RAG (top {k}, index_consistent={report.consistent}) ==="]
        ranked: list[tuple[float, int]] = []
        for idx in range(len(scores)):
            path = str(valid[idx].get("file", "")).replace("\\", "/")
            if self._should_skip_rag_path(path):
                continue
            sim = float(scores[idx])
            sim += self._rag_path_boost(path)
            ranked.append((sim, idx))
        if not ranked:
            for idx in range(len(scores)):
                ranked.append((float(scores[idx]), idx))
        ranked.sort(key=lambda x: -x[0])
        ranked = ranked[:k]

        for rank, (sim, idx) in enumerate(ranked, start=1):
            entry = valid[int(idx)]
            lines.append(
                f"\n[{rank}] sim={sim:.4f} file={entry.get('file')} "
                f"lines={entry.get('lines')}\n```\n{entry.get('text', '')[:2000]}\n```"
            )
        return "\n".join(lines)

    @staticmethod
    def _should_skip_rag_path(path: str) -> bool:
        skip_markers = (
            "/file_snapshots/",
            "/state/file_snapshots/",
            "__pycache__",
            ".pytest_cache",
            "codebase_vectors.json",
        )
        return any(m in path for m in skip_markers)

    @staticmethod
    def _rag_path_boost(path: str) -> float:
        lower = path.lower()
        boost = 0.0
        if "vault_equity" in lower:
            boost += 0.12
        if lower.startswith("generated/"):
            boost += 0.05
        if "01_hermes" in lower or "02_hermes" in lower or "03_hermes" in lower:
            boost += 0.08
        if "/file_snapshots/" in lower:
            boost -= 0.25
        return boost
