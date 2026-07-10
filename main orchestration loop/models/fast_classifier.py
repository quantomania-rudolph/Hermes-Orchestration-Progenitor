"""Fast classifier tier for T18 first-pass (falls back to Hermes 14B)."""

from __future__ import annotations

from models.hermes import HermesModel
from models.schema_contracts.base import SchemaViolation, TriageVerdict


class FastClassifier:
    def classify_triage(self, wrapped_prompt: str) -> TriageVerdict:
        model = HermesModel()
        try:
            resp = model.call(
                wrapped_prompt + "\n\nRespond ONLY with JSON: "
                '{"classification":"CODE_BUG"|"PLAN_OMISSION","confidence":0.0-1.0}',
                output_schema=TriageVerdict,
                max_tokens=128,
                temperature=0.0,
            )
            if resp.parsed:
                return resp.parsed
        except SchemaViolation:
            pass
        return TriageVerdict(classification="CODE_BUG", confidence=0.4)
