#!/usr/bin/env python3
"""Verify the 10 adversarial-gap fixes and §17 final review extensions."""

from __future__ import annotations

import inspect
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

LOOP_DIR = Path(__file__).resolve().parents[1]
HERMES_ROOT = LOOP_DIR.parent
sys.path.insert(0, str(LOOP_DIR))
sys.path.insert(0, str(HERMES_ROOT))

from orchestrator.contracts import (  # noqa: E402
    transition_p1_p2,
    transition_p3_p4,
    transition_p4_p5,
    transition_p5_p1,
)
from orchestrator.final_review import (  # noqa: E402
    _audit_journal,
    _audit_objective_clauses,
    run_final_robustness_review,
)
from orchestrator.tool_gate import PHASE_TOOL_ALLOWLIST  # noqa: E402
from tools.context.t06_ast_mapper import ASTMapper, _DI_PATTERNS  # noqa: E402
from tools.orchestration.t30_human_escalation import HumanEscalation  # noqa: E402
from tools.verification.t14_diff_analyzer import DiffAnalyzer  # noqa: E402
from tools.verification.t17_fuzzer import DataFuzzer  # noqa: E402


def main() -> int:
    print("=== verify_adversarial_completeness ===")
    failures: list[str] = []

    fuzzer = DataFuzzer()
    if not hasattr(fuzzer, "run_fuzz_for_step"):
        failures.append("T17 missing run_fuzz_for_step")
    src = inspect.getsource(DataFuzzer._fuzz_http_routes)
    if "TestClient" not in src:
        failures.append("T17 missing HTTP route fuzz via TestClient")

    t14 = DiffAnalyzer()
    if not hasattr(t14, "_ast_signature"):
        failures.append("T14 missing AST signature normalization")
    if not hasattr(t14, "cumulative_macro_audit"):
        failures.append("T14 missing cumulative_macro_audit for §17")

    if "pass" in inspect.getsource(transition_p1_p2.assert_exit):
        if "active_step_id" not in inspect.getsource(transition_p1_p2.assert_exit):
            failures.append("T29 P1->P2 assert_exit still hollow")
    if "pass" in inspect.getsource(transition_p3_p4.check_entry):
        failures.append("T29 P3->P4 check_entry still hollow")
    if "pass" in inspect.getsource(transition_p4_p5.assert_exit):
        failures.append("T29 P4->P5 assert_exit still hollow")
    if "pass" in inspect.getsource(transition_p5_p1.assert_exit):
        failures.append("T29 P5->P1 assert_exit still hollow")

    if "T03" not in PHASE_TOOL_ALLOWLIST.get(__import__("tools.common", fromlist=["Phase"]).Phase.P2, ()):
        failures.append("T27 P2 allowlist missing T03")
    if "T08" not in PHASE_TOOL_ALLOWLIST.get(__import__("tools.common", fromlist=["Phase"]).Phase.P3, ()):
        failures.append("T27 P3 allowlist missing T08")

    t30_src = inspect.getsource(HumanEscalation._dispatch_human_channels)
    if "HERMES_ALERT_WEBHOOK" not in t30_src:
        failures.append("T30 missing webhook channel")

    if not _DI_PATTERNS:
        failures.append("T06 missing DI fallback patterns")
    mapper = ASTMapper(HERMES_ROOT, LOOP_DIR / "state" / "ast_map_test.json")
    gen_src = inspect.getsource(mapper._iter_python_files)
    if "HERMES_OUTPUT_SLUG" not in gen_src:
        failures.append("T06 missing generated slug scan")

    state = {
        "core_objective": {
            "text": "BUILD TRADING ENGINE with backtest module and orchestration loop.",
            "hash": "x",
            "locked": True,
        },
        "master_plan": [
            {
                "step_id": "S001",
                "title": "trading engine",
                "intent": "build trading engine core with backtest orchestration",
                "status": "green",
            }
        ],
        "journal": [{"transition_type": "P0_COMPLETE"}],
        "wal": {"intent_to_integrate": None},
        "strike_ledger": {},
        "runtime": {},
        "genesis_baseline": {"authorized_dirs": ["generated/"]},
    }
    if not _audit_journal({}):
        failures.append("§17 journal audit should fail on empty journal")
    if _audit_objective_clauses(state):
        failures.append("§17 objective clause audit failed on aligned plan")

    ctx = MagicMock()
    ctx.objective_verifier.verify.return_value = True
    ctx.budget.within_cap.return_value = True
    ctx.repo_root = HERMES_ROOT
    ctx.loop_dir = LOOP_DIR
    ctx.diff_analyzer.cumulative_macro_audit.return_value = MagicMock(ok=True, violations=[])
    ctx.test_runner.run_tests.return_value = MagicMock(ok=True, output="")
    ctx.fuzzer.run_against_schemas.return_value = MagicMock(ok=True, crashes=[])
    ok, msgs = run_final_robustness_review(ctx, state)
    if not ok:
        failures.append(f"§17 final review failed smoke: {msgs}")

    with tempfile.TemporaryDirectory() as tmp:
        esc = HumanEscalation(Path(tmp))
        esc.alert("test", state)

    if failures:
        for msg in failures:
            print(f"[FAIL] {msg}")
        return 1

    print("[OK] Adversarial completeness checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
