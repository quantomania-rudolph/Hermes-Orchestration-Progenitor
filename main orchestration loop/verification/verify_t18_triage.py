#!/usr/bin/env python3
"""Verify T18 triage handles FastClassifier and Hermes escalation return shapes."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

LOOP_DIR = Path(__file__).resolve().parents[1]
HERMES_ROOT = LOOP_DIR.parent
sys.path.insert(0, str(LOOP_DIR))
sys.path.insert(0, str(HERMES_ROOT))

from models.schema_contracts.base import TriageVerdict  # noqa: E402
from tools.orchestration.t26_model_router import RoutedCall, TaskClass  # noqa: E402
from tools.verification.t18_triage_classifier import FailureTriageClassifier  # noqa: E402


def main() -> int:
    print("=== verify_t18_triage ===")
    failures: list[str] = []

    triage = FailureTriageClassifier()
    infra = triage.classify("wrap", "EADDRINUSE port 8000")
    if infra.kind != "INFRA_EVENT":
        failures.append("infra filter should classify EADDRINUSE")

    low_conf = TriageVerdict(classification="CODE_BUG", confidence=0.4)
    with patch("tools.verification.t18_triage_classifier.FastClassifier") as fc_cls:
        fc_cls.return_value.classify_triage.return_value = low_conf
        router = MagicMock()
        router.route_hermes.return_value = RoutedCall(
            "hermes14b", TriageVerdict(classification="PLAN_OMISSION", confidence=0.85)
        )
        triage.model_router = router
        result = triage.classify("wrap", "AssertionError: expected 1 got 0")
        if result.classification != "PLAN_OMISSION":
            failures.append(f"escalation expected PLAN_OMISSION, got {result.classification}")
        router.route_hermes.assert_called_once()
        if router.route_hermes.call_args[0][0] != TaskClass.DECISION_CLASSIFY:
            failures.append("T18 should escalate via DECISION_CLASSIFY")

    with patch("tools.verification.t18_triage_classifier.FastClassifier") as fc_cls:
        fc_cls.return_value.classify_triage.return_value = low_conf
        router = MagicMock()
        router.route_hermes.return_value = RoutedCall("fast", low_conf)
        triage.model_router = router
        result = triage.classify("wrap", "ValueError: bad arg")
        if result.classification != "CODE_BUG":
            failures.append("fast-tier TriageVerdict result should be accepted")

    if failures:
        for msg in failures:
            print(f"[FAIL] {msg}")
        return 1

    print("[OK] T18 triage escalation paths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
