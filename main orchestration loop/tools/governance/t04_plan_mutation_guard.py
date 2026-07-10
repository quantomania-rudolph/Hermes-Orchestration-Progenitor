"""T04 — Plan-Mutation Guard."""

from __future__ import annotations

import graphlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from tools.common import sha256_json, ToolError, ToolResult


DELTA_REASONS = {
    "NEW_CONSTRAINT_DISCOVERED",
    "DEPENDENCY_REORDER",
    "SCOPE_CLARIFICATION",
}


class PlanMutationGuard:
    def __init__(self, genesis_path: Path, last_good_plan_path: Path) -> None:
        self.genesis_path = genesis_path
        self.last_good_plan_path = last_good_plan_path

    def capture_genesis_baseline(self, state: dict[str, Any]) -> dict[str, Any]:
        plan = state.get("master_plan", [])
        dirs: set[str] = set()
        for step in plan:
            for tf in step.get("target_files", []):
                parts = Path(tf).parts
                if parts:
                    dirs.add(parts[0] + ("/" if len(parts) > 1 else ""))
        prior = state.get("genesis_baseline") or {}
        baseline = {
            "step_count": len(plan),
            "max_step_growth_pct": prior.get("max_step_growth_pct", 25),
            "authorized_dirs": sorted(set(prior.get("authorized_dirs", [])) | dirs),
            "objective_hash": (state.get("core_objective") or {}).get("hash", ""),
        }
        if prior.get("output_slug"):
            baseline["output_slug"] = prior["output_slug"]
        if "wipe_on_complete" in prior:
            baseline["wipe_on_complete"] = prior["wipe_on_complete"]
        self.genesis_path.parent.mkdir(parents=True, exist_ok=True)
        self.genesis_path.write_text(json.dumps(baseline, indent=2), encoding="utf-8")
        state = deepcopy(state)
        state["genesis_baseline"] = baseline
        return state

    def _load_baseline(self) -> dict[str, Any]:
        if not self.genesis_path.is_file():
            raise ToolError("genesis_baseline.json missing — run P0 capture first")
        return json.loads(self.genesis_path.read_text(encoding="utf-8"))

    def validate_mutation(
        self,
        state: dict[str, Any],
        proposed_plan: list[dict[str, Any]],
        *,
        justification: str,
        delta_reason: str,
        repo_root: Path,
    ) -> ToolResult:
        if not justification.strip():
            return ToolResult(False, {}, "Missing justification")
        if delta_reason not in DELTA_REASONS:
            return ToolResult(False, {}, f"Invalid delta_reason: {delta_reason}")

        baseline = self._load_baseline()
        genesis_count = int(baseline.get("step_count", 0))
        max_growth = int(baseline.get("max_step_growth_pct", 25))
        authorized = set(baseline.get("authorized_dirs", []))

        if genesis_count > 0:
            growth_pct = ((len(proposed_plan) - genesis_count) / genesis_count) * 100
            if growth_pct > max_growth:
                return ToolResult(
                    False,
                    {},
                    f"Macro-envelope breach: step growth {growth_pct:.1f}% > {max_growth}%",
                )

        for step in proposed_plan:
            for tf in step.get("target_files", []):
                if not any(tf.startswith(d) for d in authorized):
                    return ToolResult(
                        False,
                        {},
                        f"Macro-envelope breach: {tf} outside authorized_dirs",
                    )

        try:
            self._topo_sort(proposed_plan)
        except ToolError as exc:
            return ToolResult(False, {}, str(exc))

        provisioned = self._apply_virtual_provisioning(proposed_plan, repo_root)
        diff_hash = sha256_json(
            {"from": state.get("master_plan", []), "to": provisioned}
        )

        self.last_good_plan_path.parent.mkdir(parents=True, exist_ok=True)
        self.last_good_plan_path.write_text(
            json.dumps(state.get("master_plan", []), indent=2), encoding="utf-8"
        )

        return ToolResult(
            True,
            {
                "proposed_plan": provisioned,
                "proposed_diff_sha256": diff_hash,
            },
            "Plan mutation passed deterministic guard",
        )

    def _topo_sort(self, plan: list[dict[str, Any]]) -> list[str]:
        ids = {s["step_id"] for s in plan}
        graph: dict[str, list[str]] = {s["step_id"]: list(s.get("depends_on", [])) for s in plan}
        for sid, deps in graph.items():
            for dep in deps:
                if dep not in ids:
                    raise ToolError(f"Forward reference: {sid} depends on missing {dep}")
        sorter = graphlib.TopologicalSorter(graph)
        try:
            return list(sorter.static_order())
        except graphlib.CycleError as exc:
            raise ToolError(f"Dependency cycle: {exc}") from exc

    def _apply_virtual_provisioning(
        self, plan: list[dict[str, Any]], repo_root: Path
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for step in plan:
            s = deepcopy(step)
            bounds = list(s.get("line_bounds", [0, -1]))
            for tf in s.get("target_files", []):
                path = repo_root / tf
                if not path.is_file():
                    bounds = [0, -1]
                    break
            s["line_bounds"] = bounds
            out.append(s)
        return out

    def topo_sort_pending(self, state: dict[str, Any]) -> list[str]:
        pending = [s for s in state.get("master_plan", []) if s.get("status") == "pending"]
        return self._topo_sort(pending)
