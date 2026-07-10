"""T05 — Horizon Window Controller."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from tools.common import ToolError
from tools.governance.t04_plan_mutation_guard import PlanMutationGuard


class HorizonWindowController:
    def __init__(
        self,
        window_size: int,
        horizon_open_path: Path,
        mutation_guard: PlanMutationGuard,
    ) -> None:
        self.window_size = window_size
        self.horizon_open_path = horizon_open_path
        self.mutation_guard = mutation_guard

    def select_window(
        self,
        state: dict[str, Any],
        *,
        git_ref: str | None = None,
        forced_lookback_step: str | None = None,
    ) -> dict[str, Any]:
        state = deepcopy(state)
        horizon = dict(state.get("horizon") or {})

        if forced_lookback_step:
            for step in state.get("master_plan", []):
                if step.get("step_id") == forced_lookback_step:
                    step["status"] = "pending"
            horizon["cursor"] = forced_lookback_step
            horizon["cursor_locked"] = True

        ordered = self.mutation_guard.topo_sort_pending(state)
        window = ordered[: self.window_size]
        horizon["window"] = window
        horizon["cursor"] = window[0] if window else None
        horizon["wipe_due"] = False
        state["horizon"] = horizon

        snap = {
            "window": window,
            "git_ref": git_ref,
            "plan_step_count": len(state.get("master_plan", [])),
        }
        self.horizon_open_path.parent.mkdir(parents=True, exist_ok=True)
        self.horizon_open_path.write_text(json.dumps(snap, indent=2), encoding="utf-8")
        return state

    def strip_context_for_hermes(self, state: dict[str, Any]) -> dict[str, Any]:
        """Return a view with only horizon-visible steps for model context."""
        window = set((state.get("horizon") or {}).get("window") or [])
        visible = []
        for step in state.get("master_plan", []):
            sid = step.get("step_id")
            if sid in window:
                visible.append(deepcopy(step))
            elif step.get("status") not in ("green",):
                visible.append(
                    {
                        "step_id": sid,
                        "status": "out-of-context",
                        "title": step.get("title", ""),
                    }
                )
        view = deepcopy(state)
        view["master_plan"] = visible
        return view

    def mark_wipe_due(self, state: dict[str, Any]) -> dict[str, Any]:
        state = deepcopy(state)
        horizon = dict(state.get("horizon") or {})
        horizon["wipe_due"] = True
        state["horizon"] = horizon
        return state

    def window_exhausted(self, state: dict[str, Any]) -> bool:
        window = (state.get("horizon") or {}).get("window") or []
        return len(window) == 0

    def project_complete(self, state: dict[str, Any]) -> bool:
        plan = state.get("master_plan", [])
        if not plan:
            return False
        return all(s.get("status") == "green" for s in plan)
