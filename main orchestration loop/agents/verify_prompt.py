"""Agent_Reviewer plan-state verification prompt (T10 mode §4.4)."""

from __future__ import annotations

import json
from typing import Any


def build_verify_prompt(
    objective: str,
    current_plan: list[dict[str, Any]],
    proposed_plan: list[dict[str, Any]],
    diff_sha256: str,
) -> str:
    return (
        "Plan-state verification mode. You write NOTHING to disk.\n"
        "Return ONLY JSON:\n"
        '{"verdict":"APPROVE"|"REJECT","reason":"...","approved_diff_sha256":"sha256:..."}\n\n'
        f"## Objective\n{objective}\n\n"
        f"## Proposed diff hash\n{diff_sha256}\n\n"
        f"## Current plan (excerpt)\n{json.dumps(current_plan[:5], indent=2)}\n\n"
        f"## Proposed plan (excerpt)\n{json.dumps(proposed_plan[:5], indent=2)}\n"
    )
