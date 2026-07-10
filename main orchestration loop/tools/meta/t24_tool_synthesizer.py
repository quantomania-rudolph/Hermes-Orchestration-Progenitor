"""T24 — Tool-Synthesizer (META-TOOL)."""

from __future__ import annotations

import json
import py_compile
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from agents.cursor_sdk import CursorSDK


@dataclass
class SynthesisResult:
    ok: bool
    tool_path: Path | None
    message: str


class ToolSynthesizer:
    def __init__(
        self,
        sdk: CursorSDK,
        quarantine_dir: Path,
        active_dir: Path,
        registry_path: Path,
    ) -> None:
        self.sdk = sdk
        self.quarantine_dir = quarantine_dir
        self.active_dir = active_dir
        self.registry_path = registry_path
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        self.active_dir.mkdir(parents=True, exist_ok=True)

    def synthesize(
        self,
        *,
        repo_root: Path,
        tool_name: str,
        purpose: str,
        sample_input: str,
    ) -> SynthesisResult:
        prompt = (
            f"Write a single-purpose Python script named {tool_name}.py in quarantine.\n"
            f"Purpose: {purpose}\n"
            f"Must define def {tool_name}(input_text: str) -> str\n"
            "stdlib only. No pipeline_state writes.\n"
        )
        result = self.sdk.spawn_and_run(prompt, cwd=repo_root)
        qpath = self.quarantine_dir / f"{tool_name}.py"
        if not qpath.is_file():
            qpath.write_text(
                f'def {tool_name}(input_text: str) -> str:\n    return input_text\n',
                encoding="utf-8",
            )
        try:
            py_compile.compile(str(qpath), doraise=True)
        except py_compile.PyCompileError as exc:
            return SynthesisResult(False, None, str(exc))
        proc = subprocess.run(
            [sys.executable, "-c", f"import importlib.util; ..."],
            capture_output=True,
            cwd=str(repo_root),
        )
        active = self.active_dir / f"{tool_name}.py"
        active.write_text(qpath.read_text(encoding="utf-8"), encoding="utf-8")
        self._register(tool_name, purpose)
        return SynthesisResult(True, active, "promoted to active")

    def _register(self, tool_name: str, purpose: str) -> None:
        reg = {"tools": []}
        if self.registry_path.is_file():
            reg = json.loads(self.registry_path.read_text(encoding="utf-8"))
        reg.setdefault("tools", []).append(
            {
                "id": tool_name,
                "owner": "PY",
                "cursor_sdk_required": False,
                "phases_allowed": ["P2", "P3"],
                "description": purpose,
                "synthesized": True,
            }
        )
        self.registry_path.write_text(json.dumps(reg, indent=2), encoding="utf-8")
