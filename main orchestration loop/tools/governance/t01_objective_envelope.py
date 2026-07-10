"""T01 — Objective Envelope Wrapper."""

from __future__ import annotations

from typing import Any

from tools.common import ToolError
from tools.governance.t02_objective_hash import ObjectiveHashVerifier


class ObjectiveEnvelope:
    def __init__(self, verifier: ObjectiveHashVerifier) -> None:
        self.verifier = verifier

    def wrap(self, state: dict[str, Any], subtask: str, context_data: str) -> str:
        if not self.verifier.verify(state):
            raise ToolError("OBJECTIVE TAMPERED — halting (T02)")
        objective = (state.get("core_objective") or {}).get("text", "")
        return f"""
=========================================
SYSTEM MACRO-DIRECTIVE: CRITICAL
YOUR TARGET END-GOAL IS: {objective}
=========================================
You are navigating ONE micro-step. Every line of code and every tool call
MUST serve the Master Directive above.

Current State Context: {context_data}
Immediate Target Task: {subtask}

Respond ONLY with a tool call valid for the current phase.
"""
