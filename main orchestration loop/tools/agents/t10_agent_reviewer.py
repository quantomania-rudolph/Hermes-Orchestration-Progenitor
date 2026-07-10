"""T10 — Agent_Reviewer (code-review + plan-verify modes)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.cursor_sdk import CursorSDK
from agents.reviewer_prompt import ReviewerPromptInput, build_reviewer_prompt
from agents.verify_prompt import build_verify_prompt
from models.schema_contracts.base import PlanVerifyVerdict, SchemaViolation
from tools.context.t08_scope_boundary_compiler import AuthorizationBlock


@dataclass
class ReviewResult:
    ok: bool
    status: str
    transcript: str


class AgentReviewer:
    def __init__(self, sdk: CursorSDK) -> None:
        self.sdk = sdk

    def review_code(
        self,
        *,
        repo_root: Path,
        step_intent: str,
        auth: AuthorizationBlock,
        diff_summary: str,
        architecture_excerpt: str,
        failing_trace: str = "",
    ) -> ReviewResult:
        prompt = build_reviewer_prompt(
            ReviewerPromptInput(
                step_intent=step_intent,
                boundary_block=auth.text,
                diff_summary=diff_summary,
                architecture_excerpt=architecture_excerpt,
                failing_trace=failing_trace,
            )
        )
        result = self.sdk.spawn_and_run(prompt, cwd=repo_root)
        return ReviewResult(ok=result.status != "error", status=result.status, transcript=result.transcript)

    def verify_plan(
        self,
        *,
        repo_root: Path,
        objective: str,
        current_plan: list[dict[str, Any]],
        proposed_plan: list[dict[str, Any]],
        diff_sha256: str,
    ) -> PlanVerifyVerdict:
        prompt = build_verify_prompt(objective, current_plan, proposed_plan, diff_sha256)
        result = self.sdk.spawn_and_run(prompt, cwd=repo_root)
        try:
            return PlanVerifyVerdict.from_raw(result.transcript)
        except SchemaViolation:
            return PlanVerifyVerdict(
                verdict="REJECT",
                reason="Unparseable verifier output",
                approved_diff_sha256="sha256:invalid",
            )
