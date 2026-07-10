"""T23 — State Journal & Crash Resumption."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from tools.common import ToolError


class RecoveryAction(str, Enum):
    FRESH_START = "FRESH_START"
    RESUME_CLEAN = "RESUME_CLEAN"
    COMPLETE_INTEGRATION = "COMPLETE_INTEGRATION"
    ROLLBACK_INTEGRATION = "ROLLBACK_INTEGRATION"


@dataclass
class JournalEntry:
    timestamp: float
    phase: str
    step_id: str | None
    transition_type: str
    payload: dict[str, Any]


class StateJournal:
    def __init__(self, wal_path: Path) -> None:
        self.wal_path = wal_path
        self.wal_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.wal_path.exists():
            self.wal_path.write_text("", encoding="utf-8")

    def append_wal(self, entry: JournalEntry) -> None:
        line = json.dumps(
            {
                "timestamp": entry.timestamp,
                "phase": entry.phase,
                "step_id": entry.step_id,
                "transition_type": entry.transition_type,
                "payload": entry.payload,
            },
            separators=(",", ":"),
        )
        with self.wal_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def read_all(self) -> list[dict[str, Any]]:
        if not self.wal_path.is_file():
            return []
        entries: list[dict[str, Any]] = []
        for line in self.wal_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            entries.append(json.loads(line))
        return entries

    def write_intent_to_integrate(self, state: dict[str, Any], step_id: str) -> dict[str, Any]:
        state = dict(state)
        state["wal"] = dict(state.get("wal", {}))
        state["wal"]["intent_to_integrate"] = step_id
        self.append_wal(
            JournalEntry(
                timestamp=time.time(),
                phase="P4",
                step_id=step_id,
                transition_type="INTENT_TO_INTEGRATE",
                payload={"step_id": step_id},
            )
        )
        return state

    def clear_intent_to_integrate(self, state: dict[str, Any]) -> dict[str, Any]:
        state = dict(state)
        state["wal"] = dict(state.get("wal", {}))
        step_id = state["wal"].get("intent_to_integrate")
        state["wal"]["intent_to_integrate"] = None
        self.append_wal(
            JournalEntry(
                timestamp=time.time(),
                phase="P4",
                step_id=step_id,
                transition_type="CLEAR_INTEGRATE_INTENT",
                payload={},
            )
        )
        return state

    def detect_interrupted_run(self, state: dict[str, Any] | None) -> RecoveryAction:
        if state is None:
            return RecoveryAction.FRESH_START
        intent = (state.get("wal") or {}).get("intent_to_integrate")
        if intent:
            return RecoveryAction.COMPLETE_INTEGRATION
        journal = state.get("journal") or []
        if journal:
            return RecoveryAction.RESUME_CLEAN
        return RecoveryAction.FRESH_START

    def journal_transition(
        self,
        state: dict[str, Any],
        *,
        phase: str,
        step_id: str | None,
        transition_type: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry = JournalEntry(
            timestamp=time.time(),
            phase=phase,
            step_id=step_id,
            transition_type=transition_type,
            payload=payload or {},
        )
        self.append_wal(entry)
        state = dict(state)
        journal = list(state.get("journal") or [])
        journal.append(
            {
                "timestamp": entry.timestamp,
                "phase": entry.phase,
                "step_id": entry.step_id,
                "transition_type": entry.transition_type,
                "payload": entry.payload,
            }
        )
        state["journal"] = journal
        return state

    def execute_recovery(
        self,
        action: RecoveryAction,
        state: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if action == RecoveryAction.FRESH_START:
            if state is None:
                raise ToolError("FRESH_START requires seeded state ingestion via T03")
            return state
        if state is None:
            raise ToolError(f"Recovery {action} requires existing state")
        if action == RecoveryAction.ROLLBACK_INTEGRATION:
            state = self.clear_intent_to_integrate(state)
            self.append_wal(
                JournalEntry(
                    timestamp=time.time(),
                    phase="P4",
                    step_id=None,
                    transition_type="ROLLBACK_INTEGRATION",
                    payload={},
                )
            )
        return state
