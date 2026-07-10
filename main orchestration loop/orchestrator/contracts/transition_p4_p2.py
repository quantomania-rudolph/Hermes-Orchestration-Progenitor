"""T29 contract: P4 -> P2 (next step in window)."""

from __future__ import annotations

from tools.common import ContractViolation


def check_entry(state: dict) -> None:
    wal = (state.get("wal") or {}).get("intent_to_integrate")
    if wal:
        raise ContractViolation("P4->P2: dangling INTENT_TO_INTEGRATE WAL flag")
    window = (state.get("horizon") or {}).get("window") or []
    if not window:
        raise ContractViolation("P4->P2: horizon window empty")
    cursor = (state.get("horizon") or {}).get("cursor")
    if not cursor:
        raise ContractViolation("P4->P2: horizon cursor unset")


def assert_exit(state: dict) -> None:
    window = (state.get("horizon") or {}).get("window") or []
    cursor = (state.get("horizon") or {}).get("cursor")
    if not window or not cursor:
        raise ContractViolation("P4->P2: next window step not selected")
