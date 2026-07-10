"""Shared helpers for T29 phase-transition contracts."""

from __future__ import annotations

from typing import Any


def active_step_id(state: dict[str, Any]) -> str | None:
    runtime = state.get("runtime") or {}
    sid = runtime.get("active_step_id")
    if sid:
        return str(sid)
    return (state.get("horizon") or {}).get("cursor")


def cursor_step(state: dict[str, Any]) -> dict[str, Any] | None:
    sid = active_step_id(state)
    if not sid:
        return None
    return next(
        (s for s in state.get("master_plan", []) if s.get("step_id") == sid),
        None,
    )


def last_journal_step_status(state: dict[str, Any], step_id: str) -> str | None:
    for entry in reversed(state.get("journal") or []):
        if entry.get("step_id") != step_id:
            continue
        if entry.get("transition_type") == "STEP_STATUS":
            return (entry.get("payload") or {}).get("status")
        if entry.get("transition_type") == "GREEN_COMMIT":
            return "green"
    return None
