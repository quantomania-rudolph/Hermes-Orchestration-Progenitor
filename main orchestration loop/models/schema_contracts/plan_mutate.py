"""Schema for PLAN_GENERATE / PLAN_MUTATE Hermes output."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from models.schema_contracts.base import SchemaViolation, _extract_json_block

DELTA_REASONS = {
    "NEW_CONSTRAINT_DISCOVERED",
    "DEPENDENCY_REORDER",
    "SCOPE_CLARIFICATION",
}


@dataclass
class PlanMutateProposal:
    master_plan: list[dict[str, Any]]
    justification: str
    delta_reason: str

    @classmethod
    def from_raw(cls, text: str) -> PlanMutateProposal:
        data = _extract_json_block(text)
        plan = data.get("master_plan", [])
        if not isinstance(plan, list) or not plan:
            raise SchemaViolation("master_plan must be a non-empty list")
        for step in plan:
            if not isinstance(step, dict) or not step.get("step_id"):
                raise SchemaViolation("each master_plan step requires step_id")
        delta = str(data.get("delta_reason", "")).upper()
        if delta not in DELTA_REASONS:
            raise SchemaViolation(f"invalid delta_reason: {delta}")
        justification = str(data.get("justification", "")).strip()
        if not justification:
            raise SchemaViolation("justification required")
        return cls(master_plan=plan, justification=justification, delta_reason=delta)

    @classmethod
    def from_state(
        cls,
        state: dict[str, Any],
        *,
        justification: str,
        delta_reason: str = "SCOPE_CLARIFICATION",
    ) -> PlanMutateProposal:
        if delta_reason not in DELTA_REASONS:
            raise SchemaViolation(f"invalid delta_reason: {delta_reason}")
        return cls(
            master_plan=deepcopy(state.get("master_plan", [])),
            justification=justification,
            delta_reason=delta_reason,
        )
