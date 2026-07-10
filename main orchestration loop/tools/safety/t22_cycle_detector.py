"""T22 — Cycle / Oscillation Detector."""

from __future__ import annotations

from collections import deque
from typing import Any


class CycleDetector:
    def __init__(self, window: int = 12) -> None:
        self.window = window
        self.history: deque[str] = deque(maxlen=window)

    def record(self, transition: str) -> bool:
        self.history.append(transition)
        if len(self.history) < 4:
            return False
        items = list(self.history)
        for size in range(2, len(items) // 2 + 1):
            if items[-size:] == items[-2 * size : -size]:
                return True
        return False

    def record_phase_transition(self, state: dict[str, Any], phase: str, step_id: str | None) -> bool:
        key = f"{phase}:{step_id or '-'}"
        return self.record(key)
