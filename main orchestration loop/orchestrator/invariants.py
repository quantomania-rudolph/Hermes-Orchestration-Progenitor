"""ensure_invariants() — called at top of every master-loop iteration."""

from __future__ import annotations

from orchestrator.bootstrap import HermesContext
from tools.common import SystemHalt


def ensure_invariants(ctx: HermesContext, state: dict) -> None:
    if not ctx.objective_verifier.verify(state):
        ctx.escalation.alert("Objective hash mismatch (T02)", state)
        raise SystemHalt("Objective tampered")
    if not ctx.budget.within_cap(state):
        ctx.escalation.alert("Budget cap exceeded (T21)", state)
        raise SystemHalt("Budget killswitch")
    if ctx.phase_controller.has_dirty_contract():
        ctx.escalation.alert("Dirty phase contract (T29)", state)
        raise SystemHalt("Phase contract dirty")
