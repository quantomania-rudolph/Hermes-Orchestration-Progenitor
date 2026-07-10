"""T25 — Tool Registry & Schema Validator."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.common import Phase, ToolError


@dataclass
class ToolCallRejection:
    tool_id: str
    reason: str
    valid_for_phase: list[str]


class ToolRegistry:
    def __init__(self, static_registry_path: Path, synthesized_registry_path: Path) -> None:
        self.static_registry_path = static_registry_path
        self.synthesized_registry_path = synthesized_registry_path
        self.tools: dict[str, dict[str, Any]] = {}
        self.version = ""
        self._load()

    def _load(self) -> None:
        payload = json.loads(self.static_registry_path.read_text(encoding="utf-8"))
        self.version = payload.get("version", "unknown")
        for tool in payload.get("tools", []):
            self.tools[tool["id"]] = tool
        if self.synthesized_registry_path.is_file():
            synth = json.loads(self.synthesized_registry_path.read_text(encoding="utf-8"))
            for tool in synth.get("tools", []):
                tool["synthesized"] = True
                self.tools[tool["id"]] = tool

    def validate_tool_call(
        self, tool_id: str, current_phase: Phase | str, args: dict[str, Any] | None = None
    ) -> ToolCallRejection | None:
        phase = current_phase.value if isinstance(current_phase, Phase) else str(current_phase)
        if tool_id not in self.tools:
            return ToolCallRejection(
                tool_id,
                f"Unknown tool {tool_id}",
                self._tools_for_phase(phase),
            )
        entry = self.tools[tool_id]
        allowed = entry.get("phases_allowed", [])
        if phase not in allowed:
            return ToolCallRejection(
                tool_id,
                f"Tool {tool_id} not allowed in phase {phase}",
                allowed,
            )
        if args is not None and not isinstance(args, dict):
            return ToolCallRejection(tool_id, "args must be a dict", allowed)
        return None

    def _tools_for_phase(self, phase: str) -> list[str]:
        return sorted(
            tid
            for tid, entry in self.tools.items()
            if phase in entry.get("phases_allowed", [])
        )

    def list_phase_tools(self, phase: Phase | str) -> list[str]:
        p = phase.value if isinstance(phase, Phase) else str(phase)
        return self._tools_for_phase(p)

    def cursor_required(self, tool_id: str) -> bool:
        entry = self.tools.get(tool_id)
        if not entry:
            raise ToolError(f"Unknown tool {tool_id}")
        return bool(entry.get("cursor_sdk_required"))
