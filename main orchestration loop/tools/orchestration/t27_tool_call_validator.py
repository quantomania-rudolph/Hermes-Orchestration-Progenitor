"""T27 — Tool-Call Validator (phase-context gate)."""

from __future__ import annotations

from dataclasses import dataclass

from tools.common import Phase
from tools.meta.t25_tool_registry import ToolCallRejection, ToolRegistry


@dataclass
class ValidatedToolCall:
    tool_id: str
    args: dict


class ToolCallValidator:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def validate(
        self, tool_id: str, args: dict | None, current_phase: Phase
    ) -> ValidatedToolCall | ToolCallRejection:
        rejection = self.registry.validate_tool_call(tool_id, current_phase, args or {})
        if rejection:
            return rejection
        return ValidatedToolCall(tool_id=tool_id, args=args or {})
