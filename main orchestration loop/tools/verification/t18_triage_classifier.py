"""T18 — Failure-Triage Classifier (HERMES) + Infrastructure Error Filter."""

from __future__ import annotations

import re
from dataclasses import dataclass

from models.fast_classifier import FastClassifier
from models.hermes import HermesModel
from models.schema_contracts.base import SchemaViolation, TriageVerdict


INFRA_PATTERNS = [
    r"EADDRINUSE",
    r"database is locked",
    r"SQLite",
    r"ETIMEDOUT",
    r"ENOSPC",
    r"EACCES",
    r"Connection refused",
    r"XPU out of memory",
    r"CUDA out of memory",
]


@dataclass
class TriageResult:
    kind: str
    classification: str | None
    confidence: float
    detail: str


class FailureTriageClassifier:
    def infra_error_filter(self, normalized_signature: str) -> str | None:
        for pat in INFRA_PATTERNS:
            if re.search(pat, normalized_signature, re.I):
                return "INFRA_EVENT"
        return None

    def classify(
        self,
        wrapped_prompt: str,
        normalized_signature: str,
        *,
        synthesized_component: bool = False,
    ) -> TriageResult:
        infra = self.infra_error_filter(normalized_signature)
        if infra:
            return TriageResult(kind=infra, classification=None, confidence=1.0, detail="environmental")

        if synthesized_component:
            return TriageResult(
                kind="TOOL_DEFECT",
                classification="TOOL_DEFECT",
                confidence=0.9,
                detail="synthesized tool failure",
            )

        fast = FastClassifier()
        verdict = fast.classify_triage(
            wrapped_prompt
            + f"\n\nNormalized error signature:\n{normalized_signature}\n"
            "Classify: CODE_BUG or PLAN_OMISSION?"
        )
        if verdict.confidence < 0.6:
            try:
                model = HermesModel()
                resp = model.call(
                    wrapped_prompt
                    + f"\n\nSignature:\n{normalized_signature}\n"
                    'JSON only: {"classification":"CODE_BUG"|"PLAN_OMISSION","confidence":0.0-1.0}',
                    output_schema=TriageVerdict,
                    max_tokens=128,
                )
                if resp.parsed:
                    verdict = resp.parsed
            except SchemaViolation:
                verdict = TriageVerdict(classification="CODE_BUG", confidence=0.5)

        return TriageResult(
            kind="CLASSIFIED",
            classification=verdict.classification,
            confidence=verdict.confidence,
            detail=verdict.classification,
        )
