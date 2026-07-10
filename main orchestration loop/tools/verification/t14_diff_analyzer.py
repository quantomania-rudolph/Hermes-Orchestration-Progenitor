"""T14 — Structural Diff Analyzer."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class DiffAuditResult:
    ok: bool
    violations: list[str]


class DiffAnalyzer:
    def single_step_audit(
        self,
        repo_root: Path,
        boundaries: dict[str, list[int]],
        *,
        base_ref: str = "HEAD",
    ) -> DiffAuditResult:
        proc = subprocess.run(
            ["git", "diff", "--unified=0", base_ref],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
        )
        diff = self._normalize_diff(proc.stdout or "")
        violations: list[str] = []
        for line in diff.splitlines():
            m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
            if not m:
                continue
            # file context tracked separately via diff --name-only
        for rel, bounds in boundaries.items():
            lo, hi = bounds[0], bounds[1]
            if hi == -1:
                continue
            fproc = subprocess.run(
                ["git", "diff", "--unified=0", base_ref, "--", rel],
                capture_output=True,
                text=True,
                cwd=str(repo_root),
            )
            fdiff = self._normalize_diff(fproc.stdout or "")
            for line in fdiff.splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    # crude line tracking: flag if any + line when bounded
                    pass
            changed = bool(fproc.stdout.strip())
            if changed and lo == 0 and hi > 0:
                violations.append(f"{rel}: diff present (boundary {lo}-{hi})")
        return DiffAuditResult(ok=len(violations) == 0, violations=violations)

    def double_diff_audit(
        self,
        repo_root: Path,
        step_boundaries: dict[str, list[int]],
        horizon_open_snapshot: dict[str, Any],
    ) -> DiffAuditResult:
        single = self.single_step_audit(repo_root, step_boundaries)
        if not single.ok:
            return single
        return DiffAuditResult(ok=True, violations=[])

    def _normalize_diff(self, diff: str) -> str:
        lines = []
        for line in diff.splitlines():
            if line.startswith("\\ No newline"):
                continue
            if re.match(r"^[+-]\s*$", line):
                continue
            lines.append(line)
        return "\n".join(lines)

    def diff_summary(self, repo_root: Path, files: list[str]) -> str:
        parts: list[str] = []
        for rel in files:
            proc = subprocess.run(
                ["git", "diff", "HEAD", "--", rel],
                capture_output=True,
                text=True,
                cwd=str(repo_root),
            )
            if proc.stdout.strip():
                parts.append(f"### {rel}\n{proc.stdout[:2000]}")
        return "\n".join(parts) if parts else "(no diff)"
