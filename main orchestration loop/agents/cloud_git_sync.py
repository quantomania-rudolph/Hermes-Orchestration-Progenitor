"""Git push/pull helpers for Cursor cloud agents (edits land on remote first)."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CloudGitSyncResult:
    ok: bool
    detail: str
    branch: str = "main"


def _run_git(args: list[str], *, cwd: Path, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        timeout=timeout,
    )


def git_remote_url(repo_root: Path) -> str | None:
    proc = _run_git(["remote", "get-url", "origin"], cwd=repo_root, timeout=10)
    if proc.returncode == 0:
        return proc.stdout.strip()
    return None


def current_branch(repo_root: Path) -> str:
    proc = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root, timeout=10)
    if proc.returncode == 0:
        return proc.stdout.strip() or "main"
    return "main"


def is_git_repo(repo_root: Path) -> bool:
    return (repo_root / ".git").exists()


def prepare_for_cloud_spawn(repo_root: Path) -> CloudGitSyncResult:
    """Commit and push so the cloud VM clones up-to-date tree."""
    if not is_git_repo(repo_root):
        return CloudGitSyncResult(False, "not a git repository — run run/07_setup_git_cloud.bat first")
    remote = git_remote_url(repo_root)
    if not remote:
        return CloudGitSyncResult(
            False,
            "no git remote origin — add GitHub remote and push before cloud T09",
        )
    branch = current_branch(repo_root)

    status = _run_git(["status", "--porcelain"], cwd=repo_root)
    if status.returncode != 0:
        return CloudGitSyncResult(False, f"git status failed: {status.stderr.strip()}")

    if status.stdout.strip():
        add = _run_git(["add", "-A"], cwd=repo_root)
        if add.returncode != 0:
            return CloudGitSyncResult(False, f"git add failed: {add.stderr.strip()}")
        commit = _run_git(
            ["commit", "-m", "hermes: pre-cloud T09 sync"],
            cwd=repo_root,
        )
        if commit.returncode != 0:
            return CloudGitSyncResult(False, f"git commit failed: {commit.stderr.strip()}")

    push = _run_git(["push", "-u", "origin", branch], cwd=repo_root, timeout=180)
    if push.returncode != 0:
        return CloudGitSyncResult(
            False,
            f"git push failed: {push.stderr.strip() or push.stdout.strip()}",
            branch=branch,
        )
    return CloudGitSyncResult(True, f"pushed {branch} to origin", branch=branch)


def sync_after_cloud_spawn(
    repo_root: Path,
    *,
    target_files: list[str] | None = None,
    branch: str | None = None,
) -> CloudGitSyncResult:
    """Pull cloud agent writes back to the local checkout."""
    if not is_git_repo(repo_root):
        return CloudGitSyncResult(False, "not a git repository")
    branch = branch or current_branch(repo_root)

    fetch = _run_git(["fetch", "origin", branch], cwd=repo_root, timeout=120)
    if fetch.returncode != 0:
        return CloudGitSyncResult(False, f"git fetch failed: {fetch.stderr.strip()}", branch=branch)

    pull = _run_git(["pull", "--ff-only", "origin", branch], cwd=repo_root, timeout=120)
    if pull.returncode != 0:
        merge = _run_git(["pull", "origin", branch], cwd=repo_root, timeout=120)
        if merge.returncode != 0:
            return CloudGitSyncResult(
                False,
                f"git pull failed: {merge.stderr.strip() or merge.stdout.strip()}",
                branch=branch,
            )

    if target_files:
        missing = [rel for rel in target_files if not (repo_root / rel).is_file()]
        if missing:
            return CloudGitSyncResult(
                False,
                f"pull ok but files missing locally: {missing[:5]}",
                branch=branch,
            )

    return CloudGitSyncResult(True, f"pulled origin/{branch}", branch=branch)
