"""T28 — Decision-Paralysis Breaker."""

from __future__ import annotations

from typing import Any

from tools.common import Phase


class ParalysisBreaker:
    def apply_default(
        self,
        *,
        current_phase: Phase,
        options: list[str],
        state: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        if current_phase == Phase.P5:
            return "PLAN_PARALYSIS_ESCALATE", state
        if not options:
            return "HALT", state
        ranked = sorted(options, key=lambda o: (o.count("/"), len(o)))
        return ranked[0], state

    def plan_paralysis_override(self, state: dict[str, Any], last_good_plan_path) -> dict[str, Any]:
        import json
        from pathlib import Path

        p = Path(last_good_plan_path)
        if p.is_file():
            plan = json.loads(p.read_text(encoding="utf-8"))
            state = dict(state)
            state["master_plan"] = plan
            state.setdefault("runtime", {})["frozen"] = True
        return state
