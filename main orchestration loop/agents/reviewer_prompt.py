"""Agent_Reviewer code-review prompt builder (T10)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ReviewerPromptInput:
    step_intent: str
    boundary_block: str
    diff_summary: str
    architecture_excerpt: str
    failing_trace: str = ""


def build_reviewer_prompt(inp: ReviewerPromptInput) -> str:
    trace = f"\n## Failing trace\n{inp.failing_trace}\n" if inp.failing_trace else ""
    return (
        "You are Agent_Reviewer (fresh context). Cold critique only — patch logic holes, "
        "fix imports, reject non-conforming code. Stay within authorization boundary.\n\n"
        f"## Task\n{inp.step_intent}\n\n"
        f"## Authorization\n{inp.boundary_block}\n\n"
        f"## Diff\n{inp.diff_summary}\n\n"
        f"## Architecture rubric\n{inp.architecture_excerpt}\n"
        f"{trace}"
    )
