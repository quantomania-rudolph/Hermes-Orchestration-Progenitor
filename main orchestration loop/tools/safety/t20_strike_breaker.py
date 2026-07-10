"""T20 — Three-Strikes Loop Breaker."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from config.loop_config import THREE_STRIKES_CAP


class StrikeBreaker:
    def __init__(self, cap: int = THREE_STRIKES_CAP) -> None:
        self.cap = cap

    def record_strike(
        self, state: dict[str, Any], file_key: str, error_hash: str
    ) -> tuple[dict[str, Any], int]:
        state = deepcopy(state)
        ledger = dict(state.get("strike_ledger") or {})
        key = f"{file_key}::{error_hash}"
        count = int(ledger.get(key, 0)) + 1
        ledger[key] = count
        state["strike_ledger"] = ledger
        return state, count

    def is_strikeout(self, count: int) -> bool:
        return count >= self.cap
