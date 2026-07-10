"""T21 — Token-Burn Killswitch / Budget Accountant."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


@dataclass
class BudgetConfig:
    token_cap: int
    usd_cap: float
    floor_tokens: int
    floor_usd: float


class BudgetAccountant:
    def __init__(self, config: BudgetConfig) -> None:
        self.config = config

    def initialize(self, state: dict[str, Any]) -> dict[str, Any]:
        state = deepcopy(state)
        state["budget"] = {
            "tokens_used": 0,
            "token_cap": self.config.token_cap,
            "usd_used": 0.0,
            "usd_cap": self.config.usd_cap,
            "floor_tokens": self.config.floor_tokens,
            "floor_usd": self.config.floor_usd,
        }
        return state

    def record_usage(
        self, state: dict[str, Any], *, tokens: int = 0, usd: float = 0.0
    ) -> dict[str, Any]:
        state = deepcopy(state)
        b = dict(state.get("budget") or {})
        b["tokens_used"] = int(b.get("tokens_used", 0)) + tokens
        b["usd_used"] = float(b.get("usd_used", 0.0)) + usd
        state["budget"] = b
        return state

    def within_cap(self, state: dict[str, Any]) -> bool:
        b = state.get("budget") or {}
        return (
            int(b.get("tokens_used", 0)) < int(b.get("token_cap", self.config.token_cap))
            and float(b.get("usd_used", 0.0)) < float(b.get("usd_cap", self.config.usd_cap))
        )

    def preflight_floor_clear(self, state: dict[str, Any]) -> bool:
        b = state.get("budget") or {}
        remaining_tokens = int(b.get("token_cap", 0)) - int(b.get("tokens_used", 0))
        remaining_usd = float(b.get("usd_cap", 0.0)) - float(b.get("usd_used", 0.0))
        return (
            remaining_tokens > int(b.get("floor_tokens", self.config.floor_tokens))
            and remaining_usd > float(b.get("floor_usd", self.config.floor_usd))
        )
