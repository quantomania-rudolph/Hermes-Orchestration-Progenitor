"""T16 — Happy-Path Test Runner + Local State Purge."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TestResult:
    ok: bool
    exit_code: int
    output: str


class TestRunner:
    def local_state_purge(self, repo_root: Path) -> None:
        for name in (".pytest_cache", ".mypy_cache", ".ruff_cache"):
            p = repo_root / name
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
        tmp = repo_root / "state" / "test_tmp"
        if tmp.is_dir():
            shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True, exist_ok=True)
        for key in list(os.environ):
            if key.startswith("HERMES_TEST_"):
                os.environ.pop(key, None)

    def run_tests(self, repo_root: Path, command: str | None = None) -> TestResult:
        self.local_state_purge(repo_root)
        cmd = command or self._detect_command(repo_root)
        if not cmd:
            return TestResult(ok=True, exit_code=0, output="no test command configured")
        proc = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            timeout=300,
            env=os.environ.copy(),
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return TestResult(ok=proc.returncode == 0, exit_code=proc.returncode, output=out[-8000:])

    def _detect_command(self, repo_root: Path) -> str | None:
        generated_root = repo_root / "generated"
        if generated_root.is_dir():
            for tests_dir in sorted(generated_root.glob("*/tests")):
                if tests_dir.is_dir() and list(tests_dir.glob("test_*.py")):
                    return f'python -m pytest "{tests_dir}" -q --tb=short'
        if os.environ.get("HERMES_IN_SESSION", "").strip().lower() in {"1", "true", "yes"}:
            unit = repo_root / "main orchestration loop" / "verification"
            if unit.is_dir():
                scripts = [
                    "verify_all_tools_exist.py",
                    "verify_tool_registry.py",
                    "verify_t03_state_manager.py",
                    "verify_t04_mutation_guard.py",
                    "verify_t19_normalizer.py",
                    "verify_t20_strike_breaker.py",
                ]
                parts = [f'python "{unit / s}"' for s in scripts if (unit / s).is_file()]
                if parts:
                    return " && ".join(parts)
        if (repo_root / "pytest.ini").is_file() or list(repo_root.rglob("test_*.py")):
            return "python -m pytest -q --tb=short"
        if (repo_root / "package.json").is_file():
            return "npm test --if-present"
        verify = repo_root / "main orchestration loop" / "verification" / "run_all_verifications.py"
        if verify.is_file():
            return f'python "{verify}"'
        return None
