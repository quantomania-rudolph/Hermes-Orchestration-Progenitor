"""Forced-schema contracts for all Hermes model outputs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


class SchemaViolation(Exception):
    """Model output failed schema parse."""


def _extract_json_block(text: str) -> dict[str, Any]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    elif "{" in text:
        start = text.index("{")
        end = text.rindex("}") + 1
        text = text[start:end]
    return json.loads(text)


@dataclass
class PlanVerifyVerdict:
    verdict: str
    reason: str
    approved_diff_sha256: str

    @classmethod
    def from_raw(cls, text: str) -> PlanVerifyVerdict:
        data = _extract_json_block(text)
        verdict = str(data.get("verdict", "")).upper()
        if verdict not in {"APPROVE", "REJECT"}:
            raise SchemaViolation(f"Invalid verdict: {verdict}")
        reason = str(data.get("reason", ""))
        h = str(data.get("approved_diff_sha256", ""))
        if not h.startswith("sha256:"):
            raise SchemaViolation("approved_diff_sha256 required")
        return cls(verdict=verdict, reason=reason, approved_diff_sha256=h)


@dataclass
class TriageVerdict:
    classification: str
    confidence: float

    @classmethod
    def from_raw(cls, text: str) -> TriageVerdict:
        data = _extract_json_block(text)
        c = str(data.get("classification", data.get("verdict", ""))).upper()
        if c not in {"CODE_BUG", "PLAN_OMISSION", "TOOL_DEFECT"}:
            raise SchemaViolation(f"Invalid triage class: {c}")
        conf = float(data.get("confidence", 0.5))
        return cls(classification=c, confidence=conf)


@dataclass
class SemanticAlignResult:
    items: list[dict[str, Any]]

    @classmethod
    def from_raw(cls, text: str) -> SemanticAlignResult:
        data = _extract_json_block(text)
        items = data.get("items", data.get("checklist", []))
        if not isinstance(items, list):
            raise SchemaViolation("items must be a list")
        return cls(items=items)

    def all_pass(self) -> bool:
        return all(item.get("pass") is True or item.get("status") == "pass" for item in self.items)
