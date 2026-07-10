"""Schema for Hermes tool-call proposals (T25/T27)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from models.schema_contracts.base import SchemaViolation, _extract_json_block


@dataclass
class ToolCallProposal:
    tool_id: str
    args: dict[str, Any]

    @classmethod
    def from_raw(cls, text: str) -> ToolCallProposal:
        data = _extract_json_block(text)
        tool_id = str(data.get("tool_id", "")).upper()
        if not tool_id.startswith("T") or len(tool_id) < 2:
            raise SchemaViolation(f"invalid tool_id: {tool_id}")
        args = data.get("args", {})
        if not isinstance(args, dict):
            raise SchemaViolation("args must be an object")
        return cls(tool_id=tool_id, args=args)
