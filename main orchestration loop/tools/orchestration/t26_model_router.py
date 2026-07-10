"""T26 — Model Router & Escalation Ladder."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Type

from models.fast_classifier import FastClassifier
from models.hermes import HermesModel
from models.schema_contracts.base import SchemaViolation


class TaskClass(str, Enum):
    PLAN_GENERATE = "PLAN_GENERATE"
    PLAN_MUTATE = "PLAN_MUTATE"
    PLAN_STATE_VERIFY = "PLAN_STATE_VERIFY"
    DECISION_CLASSIFY = "DECISION_CLASSIFY"
    CODE_CREATE = "CODE_CREATE"
    CODE_REVIEW = "CODE_REVIEW"
    CODE_PATCH = "CODE_PATCH"
    SEMANTIC_ALIGN = "SEMANTIC_ALIGN"
    TOOL_SYNTHESIZE = "TOOL_SYNTHESIZE"


@dataclass
class RoutedCall:
    tier: str
    result: Any


class ModelRouter:
    ESCALATION_CAP = 2

    def route_hermes(
        self,
        task_class: TaskClass,
        wrapped_prompt: str,
        output_schema: Type[Any] | None = None,
    ) -> RoutedCall:
        if task_class == TaskClass.DECISION_CLASSIFY:
            fc = FastClassifier()
            return RoutedCall("fast", fc.classify_triage(wrapped_prompt))
        model = HermesModel()
        last_exc: Exception | None = None
        for attempt in range(self.ESCALATION_CAP + 1):
            try:
                resp = model.call(wrapped_prompt, output_schema=output_schema)
                return RoutedCall("hermes14b", resp)
            except SchemaViolation as exc:
                last_exc = exc
        raise SchemaViolation(str(last_exc))
