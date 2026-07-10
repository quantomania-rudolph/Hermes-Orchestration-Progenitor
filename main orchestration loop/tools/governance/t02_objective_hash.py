"""T02 — Core-Objective Lock & Hash Verifier."""

from __future__ import annotations

from typing import Any

from tools.common import sha256_text, ToolError


class ObjectiveHashVerifier:
    LOCKED_COPY: str | None = None

    def lock_objective(self, state: dict[str, Any]) -> dict[str, Any]:
        state = dict(state)
        obj = dict(state.get("core_objective") or {})
        text = (obj.get("text") or "").strip()
        if not text:
            raise ToolError("core_objective.text is required at genesis")
        digest = sha256_text(text)
        obj["hash"] = digest
        obj["locked"] = True
        state["core_objective"] = obj
        ObjectiveHashVerifier.LOCKED_COPY = text
        baseline = dict(state.get("genesis_baseline") or {})
        baseline["objective_hash"] = digest
        state["genesis_baseline"] = baseline
        return state

    def verify(self, state: dict[str, Any]) -> bool:
        obj = state.get("core_objective") or {}
        text = obj.get("text", "")
        stored = obj.get("hash", "")
        if not text or not stored:
            return False
        if sha256_text(text) != stored:
            return False
        if ObjectiveHashVerifier.LOCKED_COPY and text != ObjectiveHashVerifier.LOCKED_COPY:
            return False
        return True

    def restore_if_tampered(self, state: dict[str, Any]) -> dict[str, Any]:
        if self.verify(state):
            return state
        if ObjectiveHashVerifier.LOCKED_COPY is None:
            raise ToolError("Objective tampered but no locked copy available")
        state = dict(state)
        obj = dict(state.get("core_objective") or {})
        obj["text"] = ObjectiveHashVerifier.LOCKED_COPY
        obj["hash"] = sha256_text(ObjectiveHashVerifier.LOCKED_COPY)
        obj["locked"] = True
        state["core_objective"] = obj
        return state
