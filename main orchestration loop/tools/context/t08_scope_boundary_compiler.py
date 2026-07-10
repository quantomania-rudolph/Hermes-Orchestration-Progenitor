"""T08 — Scope Boundary Compiler."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class AuthorizationBlock:
    text: str
    boundaries: dict[str, list[int]]


class ScopeBoundaryCompiler:
    def compile_step(self, step: dict[str, Any], repo_root: Path) -> AuthorizationBlock:
        boundaries: dict[str, list[int]] = {}
        lines: list[str] = []
        for tf in step.get("target_files", []):
            bounds = list(step.get("line_bounds", [0, -1]))
            path = repo_root / tf
            if not path.is_file():
                bounds = [0, -1]
            lo, hi = bounds[0], bounds[1]
            boundaries[tf] = bounds
            if hi == -1:
                lines.append(f"- {tf}: lines [0, -1] (virtual provision / allow-all)")
            else:
                lines.append(f"- {tf}: lines {lo}-{hi} ONLY")
        text = (
            "AUTHORIZED EDIT BOUNDARY (machine-enforced by T14):\n"
            + "\n".join(lines)
            + "\nAny structural edit outside these ranges is a violation."
        )
        return AuthorizationBlock(text=text, boundaries=boundaries)
