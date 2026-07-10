"""T12 — Syntax / Compiler Check."""

from __future__ import annotations

import py_compile
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CompileResult:
    ok: bool
    output: str


class CompilerCheck:
    def check_files(self, repo_root: Path, files: list[str]) -> CompileResult:
        errors: list[str] = []
        for rel in files:
            path = repo_root / rel
            if not path.is_file():
                continue
            if path.suffix == ".py":
                try:
                    py_compile.compile(str(path), doraise=True)
                except py_compile.PyCompileError as exc:
                    errors.append(str(exc))
            elif path.suffix in {".ts", ".tsx"}:
                proc = subprocess.run(
                    ["npx", "tsc", "--noEmit", str(path)],
                    capture_output=True,
                    text=True,
                    cwd=str(repo_root),
                    timeout=120,
                )
                if proc.returncode != 0:
                    errors.append(proc.stderr or proc.stdout)
        if errors:
            return CompileResult(ok=False, output="\n".join(errors)[:4000])
        return CompileResult(ok=True, output="compile ok")
