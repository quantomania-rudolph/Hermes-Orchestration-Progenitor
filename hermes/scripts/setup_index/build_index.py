#!/usr/bin/env python3
"""
Incremental codebase indexer: syntax-aware chunks + local bge-m3 embeddings.

Output: codebase_vectors.json in the Hermes project root (used by hermes_orchestrator).
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Iterator

import numpy as np

HERMES_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERMES_DIR))

from hermes_config import (
    EMBED_MODEL_DEFAULT,
    HERMES_DIR as _HERMES_DIR,
    INDEX_ROOTS_DEFAULT,
    VECTORS_PATH,
)
from hermes_embeddings import embed_texts as local_embed_texts

# ── Configuration ─────────────────────────────────────────────────────────────

DEFAULT_OUTPUT = str(VECTORS_PATH)
EMBED_MODEL = os.environ.get("HERMES_EMBED_MODEL", EMBED_MODEL_DEFAULT)
TARGET_CHUNK_LINES = 40
EMBED_BATCH_SIZE = 32

SKIP_DIR_NAMES = frozenset(
    {
        "node_modules",
        ".git",
        "venv",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".eggs",
        ".tox",
        ".cursor",
        "agent-tools",
        ".idea",
        ".vscode",
        "file_snapshots",
        "alerts",
    }
)

CODE_EXTENSIONS = frozenset(
    {
        ".py",
        ".pyi",
        ".sql",
        ".ps1",
        ".sh",
        ".bash",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".md",
        ".txt",
        ".ipynb",
        ".r",
        ".go",
        ".rs",
        ".java",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        ".cs",
        ".rb",
        ".php",
        ".html",
        ".css",
        ".scss",
        ".xml",
        ".ini",
        ".cfg",
        ".env.example",
    }
)

INDEX_VERSION = 2


# ── Workspace discovery ───────────────────────────────────────────────────────


def _resolve_workspace_roots(hermes_dir: Path) -> list[Path]:
    """Resolve index roots: env var > VS Code workspace file > Hermes project dir."""
    env_roots = os.environ.get("HERMES_WORKSPACE_ROOTS", "").strip()
    if env_roots:
        return [Path(p).resolve() for p in env_roots.split(os.pathsep) if p.strip()]

    workspace_candidates = [
        hermes_dir.parent / "FILE OF DATA" / "Vault" / "FILE OF DATA.code-workspace",
        hermes_dir.parent / "Vault" / "FILE OF DATA.code-workspace",
    ]
    for workspace_file in workspace_candidates:
        if not workspace_file.is_file():
            continue
        try:
            data = json.loads(workspace_file.read_text(encoding="utf-8"))
            roots: list[Path] = []
            for folder in data.get("folders", []):
                rel = folder.get("path", ".")
                roots.append((workspace_file.parent / rel).resolve())
            if roots:
                return roots
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[warn] Could not parse {workspace_file}: {exc}", file=sys.stderr)

    default = os.environ.get("HERMES_INDEX_ROOTS_DEFAULT", INDEX_ROOTS_DEFAULT).strip()
    if default:
        return [Path(p).resolve() for p in default.split(os.pathsep) if p.strip()]
    return [hermes_dir.resolve()]


# ── Chunking ──────────────────────────────────────────────────────────────────


def _line_range_label(start: int, end: int) -> str:
    return f"{start}-{end}"


def _merge_small_spans(spans: list[tuple[int, int]], target: int) -> list[tuple[int, int]]:
    if not spans:
        return []
    merged: list[tuple[int, int]] = []
    cur_start, cur_end = spans[0]
    for n_start, n_end in spans[1:]:
        cur_len = cur_end - cur_start + 1
        next_len = n_end - n_start + 1
        if cur_len < target and cur_len + next_len <= target * 2:
            cur_end = n_end
        else:
            merged.append((cur_start, cur_end))
            cur_start, cur_end = n_start, n_end
    merged.append((cur_start, cur_end))
    return merged


def _fixed_line_chunks(lines: list[str], target: int) -> list[tuple[int, int, str]]:
    if not lines:
        return []
    chunks: list[tuple[int, int, str]] = []
    total = len(lines)
    i = 0
    while i < total:
        end = min(i + target, total)
        text = "".join(lines[i:end])
        if text.strip():
            chunks.append((i + 1, end, text))
        i = end
    return chunks


def _python_syntax_chunks(path: Path, lines: list[str], target: int) -> list[tuple[int, int, str]]:
    source = "".join(lines)
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return _fixed_line_chunks(lines, target)

    spans: list[tuple[int, int]] = []
    for node in tree.body:
        if not hasattr(node, "lineno"):
            continue
        start = node.lineno
        end = getattr(node, "end_lineno", None) or start
        spans.append((start, end))

    if not spans:
        return _fixed_line_chunks(lines, target)

    spans.sort(key=lambda s: s[0])
    spans = _merge_small_spans(spans, target)

    chunks: list[tuple[int, int, str]] = []
    cursor = 1
    for start, end in spans:
        if start > cursor:
            gap_text = "".join(lines[cursor - 1 : start - 1])
            if gap_text.strip():
                for gs, ge, gt in _fixed_line_chunks(lines[cursor - 1 : start - 1], target):
                    chunks.append((cursor + gs - 1, cursor + ge - 1, gt))
        block = lines[start - 1 : end]
        if len(block) <= target:
            text = "".join(block)
            if text.strip():
                chunks.append((start, end, text))
        else:
            for bs, be, bt in _fixed_line_chunks(block, target):
                chunks.append((start + bs - 1, start + be - 1, bt))
        cursor = end + 1

    if cursor <= len(lines):
        tail = lines[cursor - 1 :]
        for ts, te, tt in _fixed_line_chunks(tail, target):
            chunks.append((cursor + ts - 1, cursor + te - 1, tt))

    return chunks if chunks else _fixed_line_chunks(lines, target)


def chunk_file(path: Path) -> list[tuple[int, int, str]]:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"[skip] unreadable {path}: {exc}", file=sys.stderr)
        return []

    if not raw.strip():
        return []

    lines = raw.splitlines(keepends=True)
    suffix = path.suffix.lower()

    if suffix in {".py", ".pyi"}:
        spans = _python_syntax_chunks(path, lines, TARGET_CHUNK_LINES)
    elif suffix == ".ipynb":
        spans = _fixed_line_chunks(lines, TARGET_CHUNK_LINES)
    else:
        spans = _fixed_line_chunks(lines, TARGET_CHUNK_LINES)

    return spans


# ── Filesystem scan ───────────────────────────────────────────────────────────


def _should_skip_dir(dir_name: str) -> bool:
    return dir_name in SKIP_DIR_NAMES or dir_name.startswith(".")


def iter_code_files(roots: list[Path]) -> Iterator[Path]:
    for root in roots:
        if not root.is_dir():
            print(f"[warn] root missing, skipping: {root}", file=sys.stderr)
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]
            for name in filenames:
                path = Path(dirpath) / name
                if path.name == VECTORS_PATH.name:
                    continue
                if path.suffix.lower() not in CODE_EXTENSIONS:
                    continue
                try:
                    if path.stat().st_size > 2_000_000:
                        continue
                except OSError:
                    continue
                yield path.resolve()


def rel_path(path: Path, roots: list[Path]) -> str:
    for root in roots:
        try:
            return str(path.relative_to(root)).replace("\\", "/")
        except ValueError:
            continue
    return str(path)


# ── Embeddings (local sentence-transformers; NoLlama has no embed API) ────────


def embed_texts(_unused_client: object, texts: list[str]) -> list[list[float]]:
    return local_embed_texts(texts)


# ── Persistence / delta sync ───────────────────────────────────────────────────


def load_index(output_path: Path) -> tuple[dict[str, float], list[dict[str, Any]]]:
    if not output_path.is_file():
        return {}, []
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[warn] corrupt index, rebuilding: {exc}", file=sys.stderr)
        return {}, []

    registry: dict[str, float] = {}
    chunks: list[dict[str, Any]] = []

    if isinstance(payload, dict):
        registry = {k: float(v) for k, v in payload.get("file_mtimes", {}).items()}
        chunks = list(payload.get("chunks", []))
    elif isinstance(payload, list):
        chunks = payload
        for item in chunks:
            file_key = item.get("file")
            mtime = item.get("mtime")
            if file_key and mtime is not None:
                registry[file_key] = float(mtime)

    return registry, chunks


def save_index(
    output_path: Path,
    registry: dict[str, float],
    chunks: list[dict[str, Any]],
) -> None:
    payload = {
        "version": INDEX_VERSION,
        "built_at": time.time(),
        "embed_model": EMBED_MODEL,
        "embed_backend": "sentence-transformers",
        "file_mtimes": registry,
        "chunks": chunks,
    }
    tmp = output_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(output_path)


# ── Main build ────────────────────────────────────────────────────────────────


def build_index(
    roots: list[Path],
    output_path: Path,
    *,
    full_rebuild: bool = False,
) -> dict[str, int]:
    stats = {
        "scanned": 0,
        "embedded": 0,
        "reused": 0,
        "removed": 0,
        "chunks_total": 0,
    }

    registry, existing_chunks = ({}, []) if full_rebuild else load_index(output_path)
    chunks_by_file: dict[str, list[dict[str, Any]]] = {}
    for chunk in existing_chunks:
        file_key = chunk.get("file")
        if file_key:
            chunks_by_file.setdefault(file_key, []).append(chunk)

    disk_files: dict[str, Path] = {}
    disk_mtimes: dict[str, float] = {}

    for path in iter_code_files(roots):
        stats["scanned"] += 1
        key = rel_path(path, roots)
        try:
            mtime = os.path.getmtime(path)
        except OSError as exc:
            print(f"[skip] mtime {path}: {exc}", file=sys.stderr)
            continue
        disk_files[key] = path
        disk_mtimes[key] = mtime

    stale_keys = set(registry) - set(disk_files)
    for key in stale_keys:
        registry.pop(key, None)
        if key in chunks_by_file:
            del chunks_by_file[key]
            stats["removed"] += 1

    client = None
    batch_texts: list[str] = []
    batch_meta: list[tuple[str, str, str, float]] = []

    def flush_batch() -> None:
        nonlocal batch_texts, batch_meta
        if not batch_texts:
            return
        try:
            vectors = embed_texts(client, batch_texts)
        except Exception as exc:
            print(f"[error] embedding batch failed: {exc}", file=sys.stderr)
            raise
        for (file_key, lines_label, text, mtime), vector in zip(batch_meta, vectors):
            vec = np.asarray(vector, dtype=np.float32)
            norm = float(np.linalg.norm(vec))
            if norm > 0:
                vec = vec / norm
            chunks_by_file[file_key] = chunks_by_file.get(file_key, [])
            chunks_by_file[file_key] = [
                c
                for c in chunks_by_file[file_key]
                if c.get("lines") != lines_label
            ]
            chunks_by_file[file_key].append(
                {
                    "file": file_key,
                    "lines": lines_label,
                    "text": text,
                    "vector": vec.tolist(),
                    "mtime": mtime,
                }
            )
        stats["embedded"] += len(batch_texts)
        batch_texts = []
        batch_meta = []

    total_files = len(disk_files)
    for idx, (file_key, path) in enumerate(sorted(disk_files.items()), start=1):
        mtime = disk_mtimes[file_key]
        prev_mtime = registry.get(file_key)

        if not full_rebuild and prev_mtime is not None and abs(prev_mtime - mtime) < 1e-6:
            stats["reused"] += 1
            registry[file_key] = mtime
            continue

        print(f"[embed] ({idx}/{total_files}) {file_key}", flush=True)
        file_chunks = chunk_file(path)
        if not file_chunks:
            registry.pop(file_key, None)
            chunks_by_file.pop(file_key, None)
            continue

        chunks_by_file[file_key] = []
        for start, end, text in file_chunks:
            batch_texts.append(text)
            batch_meta.append((file_key, _line_range_label(start, end), text, mtime))
            if len(batch_texts) >= EMBED_BATCH_SIZE:
                flush_batch()

        registry[file_key] = mtime
        flush_batch()

    flush_batch()

    merged_chunks: list[dict[str, Any]] = []
    for file_key in sorted(chunks_by_file):
        merged_chunks.extend(chunks_by_file[file_key])

    stats["chunks_total"] = len(merged_chunks)
    save_index(output_path, registry, merged_chunks)
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Build incremental codebase vector index.")
    parser.add_argument(
        "-o",
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Output JSON path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Ignore stored mtimes and re-embed every file.",
    )
    args = parser.parse_args()

    output_path = Path(args.output).resolve()
    roots = _resolve_workspace_roots(_HERMES_DIR)

    print(f"[build_index] roots: {', '.join(str(r) for r in roots)}")
    print(f"[build_index] output: {output_path}")
    print(f"[build_index] embed: {EMBED_MODEL} (local sentence-transformers)")

    started = time.time()
    try:
        stats = build_index(roots, output_path, full_rebuild=args.full)
    except Exception as exc:
        print(f"[fatal] {exc}", file=sys.stderr)
        return 1

    elapsed = time.time() - started
    print(
        "[done] scanned={scanned} embedded={embedded} reused={reused} "
        "removed={removed} chunks={chunks_total} elapsed={elapsed:.1f}s".format(
            elapsed=elapsed, **stats
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
