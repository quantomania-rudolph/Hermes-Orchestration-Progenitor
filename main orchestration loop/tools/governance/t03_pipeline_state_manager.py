"""T03 — Pipeline State Manager (sole writer of pipeline_state.json)."""

from __future__ import annotations

import json
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any

import config.loop_config as loop_config
from tools.common import sha256_json, ToolError
from tools.safety.t23_state_journal import StateJournal


REQUIRED_TOP_KEYS = {
    "core_objective",
    "genesis_baseline",
    "master_plan",
    "horizon",
    "budget",
    "snapshots",
    "strike_ledger",
    "wal",
    "tool_registry_version",
    "journal",
}


class PipelineStateManager:
    def __init__(self, state_path: Path, journal: StateJournal) -> None:
        self.state_path = state_path
        self.journal = journal
        self._cache: dict[str, Any] | None = None

    def _validate_schema(self, state: dict[str, Any]) -> None:
        missing = REQUIRED_TOP_KEYS - set(state.keys())
        if missing:
            raise ToolError(f"pipeline_state schema missing keys: {sorted(missing)}")
        if not isinstance(state.get("master_plan"), list):
            raise ToolError("master_plan must be a list")
        for step in state["master_plan"]:
            for key in ("step_id", "title", "target_files", "status"):
                if key not in step:
                    raise ToolError(f"master_plan step missing {key}")

    def read(self) -> dict[str, Any]:
        if self._cache is not None:
            return deepcopy(self._cache)
        if not self.state_path.is_file():
            raise ToolError(f"pipeline_state not found: {self.state_path}")
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self._validate_schema(state)
        self._cache = state
        return deepcopy(state)

    def ingest_seed(self, seed_path: Path) -> dict[str, Any]:
        if not seed_path.is_file():
            raise ToolError(f"Seed file not found: {seed_path}")
        state = json.loads(seed_path.read_text(encoding="utf-8"))
        self._validate_schema(state)
        self._atomic_write(state)
        return deepcopy(state)

    def _atomic_write(self, state: dict[str, Any]) -> None:
        self._validate_schema(state)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp.replace(self.state_path)
        self._cache = deepcopy(state)

    def write_runtime_field(self, state: dict[str, Any], field: str, value: Any) -> dict[str, Any]:
        allowed = {
            "horizon",
            "budget",
            "strike_ledger",
            "journal",
            "wal",
            "snapshots",
            "runtime",
            "tool_registry_version",
        }
        if field not in allowed:
            raise ToolError(f"Field {field} is not a runtime-owned write target")
        state = deepcopy(state)
        state[field] = value
        state = self.journal.journal_transition(
            state,
            phase=(state.get("runtime") or {}).get("current_phase", "P0"),
            step_id=None,
            transition_type="RUNTIME_WRITE",
            payload={"field": field},
        )
        self._atomic_write(state)
        return state

    def write_plan_mutation(
        self,
        state: dict[str, Any],
        new_plan: list[dict[str, Any]],
        *,
        approved_diff_sha256: str,
    ) -> dict[str, Any]:
        state = deepcopy(state)
        old_plan = state.get("master_plan", [])
        diff_hash = sha256_json({"from": old_plan, "to": new_plan})
        if diff_hash != approved_diff_sha256:
            raise ToolError(
                f"Plan diff hash mismatch: expected {approved_diff_sha256}, got {diff_hash}"
            )
        state["master_plan"] = new_plan
        state = self.journal.journal_transition(
            state,
            phase=(state.get("runtime") or {}).get("current_phase", "P1"),
            step_id=None,
            transition_type="PLAN_MUTATION",
            payload={"approved_diff_sha256": approved_diff_sha256},
        )
        self._atomic_write(state)
        return state

    def write_step_status(
        self, state: dict[str, Any], step_id: str, status: str
    ) -> dict[str, Any]:
        """Python-owned step status transition (not a plan mutation)."""
        state = deepcopy(state)
        updated = False
        for step in state.get("master_plan", []):
            if step.get("step_id") == step_id:
                step["status"] = status
                updated = True
                break
        if not updated:
            raise ToolError(f"Step {step_id} not found for status update")
        state = self.journal.journal_transition(
            state,
            phase=(state.get("runtime") or {}).get("current_phase", "P2"),
            step_id=step_id,
            transition_type="STEP_STATUS",
            payload={"status": status},
        )
        self._atomic_write(state)
        return state

    def write_green_commit(self, state: dict[str, Any], step_id: str) -> dict[str, Any]:
        state = deepcopy(state)
        updated = False
        for step in state.get("master_plan", []):
            if step.get("step_id") == step_id:
                step["status"] = "green"
                updated = True
        if not updated:
            raise ToolError(f"Step {step_id} not found for green commit")
        horizon = dict(state.get("horizon") or {})
        window = list(horizon.get("window") or [])
        if window and window[0] == step_id:
            window = window[1:]
        horizon["window"] = window
        horizon["cursor"] = window[0] if window else None
        state["horizon"] = horizon
        state = self.journal.journal_transition(
            state,
            phase="P4",
            step_id=step_id,
            transition_type="GREEN_COMMIT",
            payload={"step_id": step_id},
        )
        self._atomic_write(state)
        return state

    def backup_to(self, dest: Path) -> None:
        if self.state_path.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.state_path, dest)

    def wipe_completed_session(self) -> None:
        """Delete active session state after successful external generation."""
        if self.state_path.is_file():
            self.state_path.unlink()
        self._cache = None
        for sidecar in (
            loop_config.GENESIS_BASELINE_PATH,
            loop_config.LAST_GOOD_PLAN_PATH,
            loop_config.HORIZON_OPEN_PATH,
        ):
            if sidecar.is_file():
                sidecar.unlink()
