"""T27 phase tool gating — enforce registry in phase hot paths."""

from __future__ import annotations

from tools.common import Phase, SystemHalt
from tools.meta.t25_tool_registry import ToolCallRejection
from tools.orchestration.t27_tool_call_validator import ToolCallValidator


# Tools each phase invokes directly (synced with phase modules + session.py)
PHASE_TOOL_ALLOWLIST: dict[Phase, frozenset[str]] = {
    Phase.P0: frozenset({"T02", "T03", "T04", "T06", "T07", "T11", "T21", "T23", "T25", "T27"}),
    Phase.P1: frozenset(
        {
            "T01",
            "T02",
            "T03",
            "T04",
            "T05",
            "T07",
            "T10",
            "T11",
            "T21",
            "T22",
            "T26",
            "T27",
            "T28",
            "T29",
        }
    ),
    Phase.P2: frozenset(
        {
            "T01",
            "T03",
            "T06",
            "T07",
            "T08",
            "T09",
            "T10",
            "T11",
            "T12",
            "T13",
            "T14",
            "T15",
            "T19",
            "T20",
            "T21",
            "T22",
            "T26",
            "T27",
        }
    ),
    Phase.P3: frozenset(
        {
            "T01",
            "T08",
            "T10",
            "T11",
            "T15",
            "T16",
            "T17",
            "T18",
            "T19",
            "T20",
            "T22",
            "T26",
            "T27",
            "T30",
        }
    ),
    Phase.P4: frozenset({"T03", "T06", "T07", "T14", "T15", "T22", "T23", "T27", "T29"}),
    Phase.P5: frozenset(
        {
            "T01",
            "T02",
            "T03",
            "T04",
            "T05",
            "T06",
            "T10",
            "T11",
            "T22",
            "T26",
            "T27",
            "T28",
            "T30",
        }
    ),
}


class PhaseToolGate:
    def __init__(self, validator: ToolCallValidator) -> None:
        self.validator = validator

    def assert_phase_tools(self, phase: Phase) -> None:
        """Validate allowlisted tools are legal for this phase via T27/T25."""
        allowed = PHASE_TOOL_ALLOWLIST.get(phase, frozenset())
        for tool_id in sorted(allowed):
            result = self.validator.validate(tool_id, {}, phase)
            if isinstance(result, ToolCallRejection):
                raise SystemHalt(
                    f"T27 phase gate: {tool_id} wired in {phase.value} but rejected — {result.reason}"
                )

    def assert_tool(self, tool_id: str, phase: Phase, args: dict | None = None) -> None:
        result = self.validator.validate(tool_id, args or {}, phase)
        if isinstance(result, ToolCallRejection):
            raise SystemHalt(f"T27 rejected {tool_id} in {phase.value}: {result.reason}")
