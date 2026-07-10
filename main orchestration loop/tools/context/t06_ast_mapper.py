"""T06 — AST Dependency-Tree Mapper."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any


class ASTMapper:
    def __init__(self, repo_root: Path, cache_path: Path) -> None:
        self.repo_root = repo_root
        self.cache_path = cache_path

    def build_map(self, *, globs: list[str] | None = None) -> dict[str, Any]:
        interfaces: dict[str, list[str]] = {}
        for path in self._iter_python_files():
            rel = str(path.relative_to(self.repo_root)).replace("\\", "/")
            sigs = self._public_signatures(path)
            if sigs:
                interfaces[rel] = sigs
        payload = {"interfaces": interfaces, "file_count": len(interfaces)}
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    def load_map(self) -> dict[str, Any]:
        if not self.cache_path.is_file():
            return self.build_map()
        return json.loads(self.cache_path.read_text(encoding="utf-8"))

    def inject_interfaces(self, target_files: list[str]) -> str:
        amap = self.load_map()
        interfaces = amap.get("interfaces", {})
        lines: list[str] = []
        for tf in target_files:
            path = self.repo_root / tf
            if not path.is_file():
                continue
            imports = self._extract_imports(path)
            for imp in imports:
                mod = imp.replace(".", "/") + ".py"
                for key, sigs in interfaces.items():
                    if key.endswith(mod) or mod in key:
                        lines.append(f"### {key}\n" + "\n".join(sigs[:20]))
        return "\n\n".join(lines) if lines else ""

    def meta_summary(self) -> str:
        amap = self.load_map()
        interfaces = amap.get("interfaces", {})
        parts = [f"AST meta-summary: {len(interfaces)} files with public interfaces"]
        for rel, sigs in sorted(interfaces.items())[:30]:
            parts.append(f"  {rel}: {len(sigs)} signatures")
        return "\n".join(parts)

    def _iter_python_files(self) -> list[Path]:
        skip = {".git", "node_modules", "__pycache__", ".venv", "venv"}
        out: list[Path] = []
        for path in self.repo_root.rglob("*.py"):
            if any(p in skip for p in path.parts):
                continue
            out.append(path)
        return out

    def _public_signatures(self, path: Path) -> list[str]:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
        except SyntaxError:
            return []
        sigs: list[str] = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    args = [a.arg for a in node.args.args]
                    sigs.append(f"def {node.name}({', '.join(args)})")
            elif isinstance(node, ast.ClassDef):
                if not node.name.startswith("_"):
                    sigs.append(f"class {node.name}")
        return sigs

    def _extract_imports(self, path: Path) -> list[str]:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            return []
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        return imports
