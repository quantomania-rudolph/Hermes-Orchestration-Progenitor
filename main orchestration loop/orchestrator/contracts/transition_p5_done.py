"""T29 contract: P5 -> DONE."""

from __future__ import annotations

from tools.common import ContractViolation


def check_entry(state: dict) -> None:
    plan = state.get("master_plan", [])
    if plan and not all(s.get("status") == "green" for s in plan):
        raise ContractViolation("P5->DONE: not all steps green")


def assert_exit(state: dict) -> None:
    pass
