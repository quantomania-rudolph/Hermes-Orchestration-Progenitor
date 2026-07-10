"""P2 gauntlet: T14 -> T12 -> T13 (re-entry after patches)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from orchestrator.bootstrap import HermesContext
@dataclass
class GauntletResult:
    ok: bool
    stage: str
    detail: str


def run_p2_gauntlet(
    ctx: HermesContext,
    *,
    repo_root: Path,
    boundaries: dict,
    target_files: list[str],
    wrapped_prompt: str,
    code_summary: str,
) -> GauntletResult:
    diff = ctx.diff_analyzer.single_step_audit(repo_root, boundaries)
    if not diff.ok:
        return GauntletResult(False, "T14", "; ".join(diff.violations))

    compile_r = ctx.compiler.check_files(repo_root, target_files)
    if not compile_r.ok:
        return GauntletResult(False, "T12", compile_r.output)

    semantic = ctx.semantic.check(wrapped_prompt, code_summary)
    if not semantic.ok:
        return GauntletResult(False, "T13", semantic.raw[:500])

    return GauntletResult(True, "PASS", "gauntlet clear")
