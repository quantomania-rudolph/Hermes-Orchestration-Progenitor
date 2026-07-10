"""T15 — Git Snapshot & Restore."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SnapshotHandle:
    snapshot_dir: Path
    files: list[str]


class GitSnapshot:
    def __init__(self, snapshot_root: Path) -> None:
        self.snapshot_root = snapshot_root
        self.snapshot_root.mkdir(parents=True, exist_ok=True)

    def take_snapshot(self, repo_root: Path, files: list[str]) -> SnapshotHandle:
        sid = f"snap_{abs(hash(tuple(files))) % 10**8}"
        dest = self.snapshot_root / sid
        dest.mkdir(parents=True, exist_ok=True)
        for rel in files:
            src = repo_root / rel
            if src.is_file():
                out = dest / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, out)
        return SnapshotHandle(snapshot_dir=dest, files=list(files))

    def restore(self, repo_root: Path, handle: SnapshotHandle) -> None:
        for rel in handle.files:
            src = handle.snapshot_dir / rel
            dst = repo_root / rel
            if src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            elif dst.is_file():
                dst.unlink()

    def git_restore(self, repo_root: Path, files: list[str]) -> None:
        if not (repo_root / ".git").is_dir():
            return
        subprocess.run(
            ["git", "checkout", "--", *files],
            cwd=str(repo_root),
            capture_output=True,
        )

    def fast_forward_valid(self, repo_root: Path, expected_ref: str | None) -> bool:
        if not (repo_root / ".git").is_dir():
            return True
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
        )
        if proc.returncode != 0:
            return True
        current = (proc.stdout or "").strip()
        if expected_ref and "@" in expected_ref:
            expected_ref = expected_ref.split("@", 1)[1]
        if expected_ref and len(expected_ref) >= 7:
            return current.startswith(expected_ref[:7]) or expected_ref.startswith(current[:7])
        return True

    def merge_scratch(self, repo_root: Path) -> bool:
        if not (repo_root / ".git").is_dir():
            return True
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
        )
        return proc.returncode == 0
