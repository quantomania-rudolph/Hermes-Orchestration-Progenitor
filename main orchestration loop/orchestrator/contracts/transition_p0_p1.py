"""T29 contract: P0 → P1."""

from __future__ import annotations

from tools.common import ContractViolation


def check_entry(state: dict) -> None:
    obj = state.get("core_objective") or {}
    if not obj.get("locked") or not obj.get("hash"):
        raise ContractViolation("P0 incomplete: objective not hash-locked")
    baseline = state.get("genesis_baseline") or {}
    if not baseline.get("step_count"):
        raise ContractViolation("P0 incomplete: genesis_baseline not captured")
    runtime = state.get("runtime") or {}
    index = runtime.get("index") or {}
    if not index.get("vectors_path"):
        raise ContractViolation("P0 incomplete: index not linked")
    if index.get("chunk_count", 1) < 1:
        raise ContractViolation("P0 incomplete: index has no chunks")


def assert_exit(state: dict) -> None:
    window = (state.get("horizon") or {}).get("window") or []
    if not window:
        raise ContractViolation("P1 exit failed: horizon window empty")
    b = state.get("budget") or {}
    remaining_t = int(b.get("token_cap", 0)) - int(b.get("tokens_used", 0))
    remaining_u = float(b.get("usd_cap", 0)) - float(b.get("usd_used", 0))
    if remaining_t <= int(b.get("floor_tokens", 0)):
        raise ContractViolation("P1 exit failed: token budget below floor")
    if remaining_u <= float(b.get("floor_usd", 0)):
        raise ContractViolation("P1 exit failed: USD budget below floor")
