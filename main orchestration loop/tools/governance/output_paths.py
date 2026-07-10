"""Route generated artifacts outside the orchestration loop and finalize on completion."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import config.loop_config as loop_config


def output_prefix(slug: str) -> str:
    root = loop_config.GENERATED_OUTPUT_ROOT.relative_to(loop_config.HERMES_ROOT)
    return f"{root.as_posix()}/{slug}/"


def infer_slug(state: dict[str, Any]) -> str | None:
    baseline = state.get("genesis_baseline") or {}
    slug = (baseline.get("output_slug") or "").strip()
    if slug:
        return slug
    for step in state.get("master_plan", []):
        for tf in step.get("target_files", []):
            parts = Path(tf).parts
            if len(parts) >= 2 and parts[0] in {"projects", "generated"}:
                return parts[1]
    return None


def is_external_generation(state: dict[str, Any]) -> bool:
    return bool((state.get("genesis_baseline") or {}).get("output_slug"))


def should_wipe_on_complete(state: dict[str, Any]) -> bool:
    if not is_external_generation(state):
        return False
    baseline = state.get("genesis_baseline") or {}
    if baseline.get("wipe_on_complete") is False:
        return False
    if loop_config.is_dry_run():
        return False
    return True


def bind_generated_output(state: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    """Rewrite plan paths so deliverables land under HERMES_ROOT/generated/<slug>/."""
    slug = infer_slug(state)
    if not slug:
        return state

    state = deepcopy(state)
    prefix = output_prefix(slug)
    old_prefixes = (
        f"projects/{slug}/",
        f"generated/{slug}/",
        prefix,
    )

    def remap_path(path: str) -> str:
        p = path.replace("\\", "/")
        for old in old_prefixes:
            if p.startswith(old):
                return prefix + p[len(old) :]
        if "/" not in p:
            return prefix + p
        parts = Path(p).parts
        if parts and parts[0] not in {"main orchestration loop", "generated", "projects"}:
            return prefix + p
        return p

    for step in state.get("master_plan", []):
        step["target_files"] = [remap_path(tf) for tf in step.get("target_files", [])]
        intent = step.get("intent", "")
        for old in (f"projects/{slug}", f"generated/{slug}"):
            intent = intent.replace(old, prefix.rstrip("/"))
        step["intent"] = intent

    baseline = dict(state.get("genesis_baseline") or {})
    baseline["output_slug"] = slug
    baseline["authorized_dirs"] = [prefix]
    state["genesis_baseline"] = baseline

    out_dir = loop_config.GENERATED_OUTPUT_ROOT / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    runtime = dict(state.get("runtime") or {})
    runtime["output_root"] = str(out_dir.relative_to(repo_root))
    runtime["output_slug"] = slug
    state["runtime"] = runtime
    print(f"[P0] Generated output bound to {out_dir}")
    return state


def finalize_completed_session(ctx: Any, state: dict[str, Any]) -> None:
    """Wipe pipeline_state.json after external project generation completes."""
    if not should_wipe_on_complete(state):
        return

    runtime = state.get("runtime") or {}
    output_root = runtime.get("output_root", "")
    ctx.journal.journal_transition(
        state,
        phase="DONE",
        step_id=None,
        transition_type="SESSION_WIPE",
        payload={"output_root": output_root},
    )
    ctx.state_manager.wipe_completed_session()
    print(f"[session] Deliverables retained at {output_root or loop_config.GENERATED_OUTPUT_ROOT}")
    print("[session] pipeline_state.json wiped — ready for next seed")
