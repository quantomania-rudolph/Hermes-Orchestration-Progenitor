#!/usr/bin/env python3
"""
Hermes preflight: verify packages, paths, NoLlama, index, and Cursor SDK readiness.

  python hermes_preflight.py
  python hermes_preflight.py --quick    # skip slow NoLlama chat probe
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Literal

from hermes_secrets import load_local_env

load_local_env()

from hermes_config import (
    BUILD_INDEX_SCRIPT,
    CURSOR_MODEL_DEFAULT,
    EMBED_MODEL_DEFAULT,
    HERMES_CHAT_MODEL_DEFAULT,
    HERMES_DIR,
    NOLLAMA_HEALTH_URL,
    NOLLAMA_OPENAI_BASE_URL,
    VECTORS_PATH,
    WORKSPACE_ROOT,
)

WORKSPACE_FILE = Path(r"C:/Users/Rudol/Desktop/FILE OF DATA/Vault/FILE OF DATA.code-workspace")
from hermes_nollama import resolve_chat_model

NOLLAMA_CHAT_URL = os.environ.get("NOLLAMA_OPENAI_BASE_URL", NOLLAMA_OPENAI_BASE_URL)
CHAT_MODEL = os.environ.get("HERMES_CHAT_MODEL", HERMES_CHAT_MODEL_DEFAULT)
EMBED_MODEL = os.environ.get("HERMES_EMBED_MODEL", EMBED_MODEL_DEFAULT)
CURSOR_MODEL = os.environ.get("HERMES_CURSOR_MODEL", CURSOR_MODEL_DEFAULT)

Status = Literal["OK", "WARN", "FAIL"]


class CheckResult:
    def __init__(self, name: str, status: Status, detail: str) -> None:
        self.name = name
        self.status = status
        self.detail = detail


results: list[CheckResult] = []


def record(name: str, status: Status, detail: str) -> None:
    results.append(CheckResult(name, status, detail))
    tag = {"OK": "[OK]", "WARN": "[WARN]", "FAIL": "[FAIL]"}[status]
    print(f"{tag} {name}")
    for line in detail.splitlines():
        print(f"      {line}")


def http_get_json(url: str, timeout: float = 10.0) -> dict | list | None:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def check_python_packages() -> None:
    missing: list[str] = []
    for mod, pip_name in (
        ("numpy", "numpy"),
        ("openai", "openai"),
        ("cursor_sdk", "cursor-sdk"),
        ("sentence_transformers", "sentence-transformers"),
    ):
        try:
            __import__(mod)
        except ImportError:
            missing.append(pip_name)
    if missing:
        record(
            "Python packages",
            "FAIL",
            f"Missing: {', '.join(missing)}\n"
            f"Install: pip install -r {HERMES_DIR / 'requirements-hermes.txt'}",
        )
    else:
        record(
            "Python packages",
            "OK",
            "numpy, openai, cursor-sdk, sentence-transformers importable",
        )


def check_paths() -> None:
    issues: list[str] = []
    if not BUILD_INDEX_SCRIPT.is_file():
        issues.append(f"Missing {BUILD_INDEX_SCRIPT.name}")
    if not WORKSPACE_ROOT.is_dir():
        issues.append(f"Workspace root not found: {WORKSPACE_ROOT}")
    if not WORKSPACE_FILE.is_file():
        issues.append(f"Workspace file not found (optional): {WORKSPACE_FILE}")
    orchestrator = HERMES_DIR / "hermes_orchestrator.py"
    if not orchestrator.is_file():
        issues.append("Missing hermes_orchestrator.py")

    if issues:
        record("Paths", "FAIL" if "Missing build_index" in str(issues) else "WARN", "\n".join(issues))
    else:
        lines = [
            f"Hermes dir:  {HERMES_DIR}",
            f"Workspace:   {WORKSPACE_ROOT}",
            f"Workspace file: {WORKSPACE_FILE.name} found",
        ]
        record("Paths", "OK", "\n".join(lines))


def check_nollama_server() -> None:
    health = http_get_json(NOLLAMA_HEALTH_URL, timeout=5.0)
    if not isinstance(health, dict):
        record(
            "NoLlama server",
            "FAIL",
            f"Cannot reach {NOLLAMA_HEALTH_URL}\n"
            "Install: https://github.com/aweussom/NoLlama\n"
            "Then: .\\install.ps1 && .\\start.ps1  (set NOLLAMA_HOME to clone path)",
        )
        return

    models_payload = http_get_json(f"{NOLLAMA_CHAT_URL.rstrip('/')}/models", timeout=5.0)
    model_ids: set[str] = set()
    if isinstance(models_payload, dict):
        for entry in models_payload.get("data", []):
            mid = entry.get("id")
            if mid:
                model_ids.add(mid)

    lines = [
        f"Health: {NOLLAMA_HEALTH_URL}",
        f"Status: {health.get('status', health)}",
        f"OpenAI models listed: {len(model_ids)}",
    ]
    resolved = resolve_chat_model(CHAT_MODEL, prefer_device="GPU")
    status: Status = "OK"
    if not resolved:
        status = "WARN"
        lines.append(f"Chat model '{CHAT_MODEL}' not resolvable from /v1/models")
        lines.append("Set HERMES_CHAT_MODEL to a loaded NoLlama model name.")
    else:
        lines.append(f"Chat model present: {resolved} (requested: {CHAT_MODEL})")

    record("NoLlama server", status, "\n".join(lines))


def check_local_embeddings() -> None:
    try:
        from hermes_embeddings import embed_texts

        vec = embed_texts(["hermes preflight probe"])[0]
        record(
            "Local RAG embeddings",
            "OK",
            f"model={EMBED_MODEL}  dimensions={len(vec)}  backend=sentence-transformers",
        )
    except Exception as exc:
        record("Local RAG embeddings", "FAIL", str(exc))


def check_nollama_chat(*, quick: bool) -> None:
    if quick:
        record(
            "NoLlama chat API",
            "WARN",
            "Skipped (--quick). Run without --quick to probe chat completions.",
        )
        return
    try:
        from openai import OpenAI

        client = OpenAI(
            base_url=NOLLAMA_CHAT_URL,
            api_key=os.environ.get("NOLLAMA_API_KEY", "nollama"),
        )
        chat_model = resolve_chat_model(CHAT_MODEL, prefer_device="GPU") or CHAT_MODEL
        resp = client.chat.completions.create(
            model=chat_model,
            messages=[{"role": "user", "content": "/no_think Reply with exactly: OK"}],
            max_tokens=32,
            temperature=0,
        )
        text = (resp.choices[0].message.content or "").strip()
        record(
            "NoLlama chat API",
            "OK",
            f"{NOLLAMA_CHAT_URL}\nmodel={chat_model}\nreply={text[:80]!r}",
        )
    except Exception as exc:
        record(
            "NoLlama chat API",
            "FAIL",
            f"{NOLLAMA_CHAT_URL}\nmodel={CHAT_MODEL}\n{exc}\n"
            "(First load after idle can take 30-60s on NPU.)",
        )


def check_vectors_index() -> None:
    if not VECTORS_PATH.is_file():
        record(
            "RAG index (codebase_vectors.json)",
            "WARN",
            f"Not found at {VECTORS_PATH}\n"
            "Run: scripts\\setup_index\\01_build_index.bat",
        )
        return
    try:
        payload = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            chunks = payload.get("chunks", [])
            registry = payload.get("file_mtimes", {})
        elif isinstance(payload, list):
            chunks = payload
            registry = {}
        else:
            raise ValueError("unexpected JSON shape")
        if not chunks:
            record(
                "RAG index (codebase_vectors.json)",
                "WARN",
                "File exists but contains zero chunks. Run: scripts\\setup_index\\01_build_index.bat",
            )
            return
        sample = chunks[0]
        has_vector = bool(sample.get("vector"))
        size_mb = VECTORS_PATH.stat().st_size / (1024 * 1024)
        record(
            "RAG index (codebase_vectors.json)",
            "OK" if has_vector else "WARN",
            f"chunks={len(chunks)}  files_in_registry={len(registry)}  "
            f"size={size_mb:.1f} MB  sample_has_vector={has_vector}",
        )
    except Exception as exc:
        record("RAG index (codebase_vectors.json)", "FAIL", str(exc))


def check_cursor_api(*, strict: bool) -> None:
    api_key = os.environ.get("CURSOR_API_KEY", "").strip()
    if not api_key:
        record(
            "Cursor API (Composer)",
            "WARN",
            "CURSOR_API_KEY not set.\n"
            "invoke_cursor_composer will fail until you export a key from Cursor Dashboard.",
        )
        return
    try:
        from cursor_sdk import Cursor

        models = Cursor.models.list(api_key=api_key)
        ids = [getattr(m, "id", str(m)) for m in models[:20]]
        has_composer = any(CURSOR_MODEL in str(mid) for mid in ids)
        detail = f"API key accepted. Listed {len(ids)} model(s) (first page)."
        if has_composer:
            detail += f"\nTarget model '{CURSOR_MODEL}' appears available."
        else:
            detail += (
                f"\nCould not confirm '{CURSOR_MODEL}' in first page; "
                "Composer may still work."
            )
        record("Cursor API (Composer)", "OK", detail)
    except Exception as exc:
        record(
            "Cursor API (Composer)",
            "FAIL" if strict else "WARN",
            f"Key is set but API check failed (Composer optional for RAG/chat):\n{exc}",
        )


def check_build_index_import() -> None:
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("build_index", BUILD_INDEX_SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load {BUILD_INDEX_SCRIPT}")
        bi = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bi)

        roots = bi._resolve_workspace_roots(HERMES_DIR)
        record(
            "build_index module",
            "OK",
            "Import OK\n"
            f"Would index {len(roots)} root(s):\n"
            + "\n".join(f"  - {r}" for r in roots),
        )
    except Exception as exc:
        record("build_index module", "FAIL", str(exc))


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes environment preflight checks.")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Skip slow NoLlama chat completion probe.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat Cursor API failures as FAIL (default: WARN).",
    )
    parser.add_argument(
        "--skip-cursor",
        action="store_true",
        help="Skip Cursor API probe (avoids slow/hanging network checks).",
    )
    args = parser.parse_args()

    print("Hermes preflight\n" + "=" * 40)

    check_python_packages()
    check_paths()
    check_build_index_import()
    check_nollama_server()
    if args.quick:
        record(
            "Local RAG embeddings",
            "WARN",
            "Skipped (--quick). First embed load downloads BAAI/bge-m3 (~1-2 min).",
        )
    else:
        check_local_embeddings()
    check_nollama_chat(quick=args.quick)
    check_vectors_index()
    if args.skip_cursor:
        record(
            "Cursor API (Composer)",
            "WARN",
            "Skipped (--skip-cursor). Set CURSOR_API_KEY before Composer runs.",
        )
    else:
        check_cursor_api(strict=args.strict)

    print("=" * 40)
    fails = [r for r in results if r.status == "FAIL"]
    warns = [r for r in results if r.status == "WARN"]
    oks = [r for r in results if r.status == "OK"]

    print(f"Summary: {len(oks)} OK, {len(warns)} WARN, {len(fails)} FAIL")
    if fails:
        print("\nFailed checks:")
        for r in fails:
            print(f"  - {r.name}")
        return 1
    if warns:
        print("\nWarnings (non-blocking):")
        for r in warns:
            print(f"  - {r.name}")
    print("\nCore stack looks ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
