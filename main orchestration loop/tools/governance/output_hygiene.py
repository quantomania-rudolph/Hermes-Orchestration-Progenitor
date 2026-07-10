"""Reject Cursor scratch files outside step target_files in generated output."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


SCRATCH_SUFFIXES = {".pl", ".sh", ".bat"}
IGNORE_PARTS = {".pytest_cache", "pytest-cache-files", "__pycache__"}


@dataclass
class HygieneResult:
    ok: bool
    stray_files: list[str]


def audit_step_outputs(repo_root: Path, target_files: list[str]) -> HygieneResult:
    allowed = {p.replace("\\", "/") for p in target_files}
    roots: set[str] = set()
    for rel in allowed:
        if rel.startswith("generated/"):
            parts = rel.split("/")
            if len(parts) >= 2:
                roots.add(f"generated/{parts[1]}")

    stray: list[str] = []
    for root_rel in sorted(roots):
        root = repo_root / root_rel
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = str(path.relative_to(repo_root)).replace("\\", "/")
            if any(part in rel for part in IGNORE_PARTS):
                continue
            if rel in allowed:
                continue
            name = path.name
            if name == "__init__.py":
                continue
            if name.startswith("_") and path.suffix == ".py":
                stray.append(rel)
                continue
            if path.suffix in SCRATCH_SUFFIXES:
                stray.append(rel)
                continue
            # Allow nested dirs explicitly listed (e.g. sample_data/*.csv)
            if any(
                rel.startswith(a.rsplit("/", 1)[0] + "/")
                for a in allowed
                if "/" in a and a.rsplit("/", 1)[0] in rel
            ):
                parent = str(Path(rel).parent).replace("\\", "/")
                if any(a.startswith(parent + "/") or a.startswith(parent) for a in allowed):
                    continue
            if rel.endswith(".csv") and "sample_data" in rel:
                continue

    return HygieneResult(ok=not stray, stray_files=sorted(stray))
