"""User-seeded plan helpers — no Hermes PLAN_GENERATE / PLAN_MUTATE."""

from __future__ import annotations

from typing import Any

from models.schema_contracts.plan_mutate import PlanMutateProposal


def identity_plan_proposal(
    state: dict[str, Any],
    *,
    justification: str,
    delta_reason: str = "SCOPE_CLARIFICATION",
) -> PlanMutateProposal:
    """Return the ingested seed plan unchanged (T04/T03 identity path)."""
    return PlanMutateProposal.from_state(
        state,
        justification=justification,
        delta_reason=delta_reason,
    )
