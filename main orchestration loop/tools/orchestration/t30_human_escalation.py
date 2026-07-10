"""T30 — Human Escalation / Alert Channel."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class HumanEscalation:
    def __init__(self, alerts_dir: Path) -> None:
        self.alerts_dir = alerts_dir
        self.alerts_dir.mkdir(parents=True, exist_ok=True)

    def alert(
        self,
        reason: str,
        state: dict[str, Any],
        *,
        extra: dict[str, Any] | None = None,
    ) -> Path:
        bundle = {
            "timestamp": time.time(),
            "reason": reason,
            "objective": (state.get("core_objective") or {}).get("text"),
            "current_phase": (state.get("runtime") or {}).get("current_phase"),
            "horizon": state.get("horizon"),
            "budget": state.get("budget"),
            "strike_ledger": state.get("strike_ledger"),
            "extra": extra or {},
        }
        path = self.alerts_dir / f"alert_{int(time.time())}.json"
        path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
        print(f"[T30 ESCALATION] {reason}")
        print(f"  Diagnostic bundle: {path}")
        return path
