"""T29 contract: P1 → P2."""

from __future__ import annotations

from tools.common import ContractViolation


def check_entry(state: dict) -> None:
    window = (state.get("horizon") or {}).get("window") or []
    if not window:
        raise ContractViolation("P1→P2: horizon window not populated")


def assert_exit(state: dict) -> None:
    # Full P2 gauntlet defers to step status; dry-run marks in_progress
    pass
