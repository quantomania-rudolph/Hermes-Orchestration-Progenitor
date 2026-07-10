"""T29 contract: P5 -> P1."""

from __future__ import annotations

from tools.common import ContractViolation


def check_entry(state: dict) -> None:
    if not (state.get("horizon") or {}).get("window"):
        raise ContractViolation("P5->P1: horizon not refreshed")


def assert_exit(state: dict) -> None:
    pass
