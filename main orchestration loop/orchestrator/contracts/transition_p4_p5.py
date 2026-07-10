"""T29 contract: P4 -> P5."""

from __future__ import annotations

from tools.common import ContractViolation


def check_entry(state: dict) -> None:
    wal = (state.get("wal") or {}).get("intent_to_integrate")
    if wal:
        raise ContractViolation("P4->P5: dangling INTENT_TO_INTEGRATE WAL flag")


def assert_exit(state: dict) -> None:
    pass
