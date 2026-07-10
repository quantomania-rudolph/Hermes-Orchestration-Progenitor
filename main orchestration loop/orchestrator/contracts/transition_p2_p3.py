"""T29 contract: P2 -> P3."""

from __future__ import annotations

from tools.common import ContractViolation


def check_entry(state: dict) -> None:
    window = (state.get("horizon") or {}).get("window") or []
    if not window:
        raise ContractViolation("P2->P3: no active horizon window")


def assert_exit(state: dict) -> None:
    pass
