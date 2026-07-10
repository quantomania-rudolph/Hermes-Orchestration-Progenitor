#!/usr/bin/env python3
"""Smoke-test every T01-T30 implementation is importable and callable."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parents[1]
HERMES_ROOT = LOOP_DIR.parent
sys.path.insert(0, str(LOOP_DIR))
sys.path.insert(0, str(HERMES_ROOT))

from hermes_secrets import load_local_env  # noqa: E402

load_local_env()

from orchestrator.bootstrap import build_context  # noqa: E402
from tools.common import Phase  # noqa: E402
import config.loop_config as lc  # noqa: E402


def main() -> int:
    print("=== verify_tool_smoke ===")
    ctx = build_context(HERMES_ROOT)
    failures: list[str] = []

    # T02 then T01 (envelope requires locked objective)
    state = json.loads((LOOP_DIR / "pipeline_state.seed.json").read_text(encoding="utf-8"))
    locked = ctx.objective_verifier.lock_objective(state)
    w = ctx.objective_envelope.wrap(locked, "sub", "")
    if "SYSTEM MACRO-DIRECTIVE" not in w:
        failures.append("T01 wrap failed")
    if not ctx.objective_verifier.verify(locked):
        failures.append("T02 lock/verify failed")

    # T03-T05 via temp state
    with tempfile.TemporaryDirectory() as tmp:
        import config.loop_config as lc

        sp = Path(tmp) / "pipeline_state.json"
        lc.PIPELINE_STATE_PATH = sp
        lc.WAL_PATH = Path(tmp) / "wal.jsonl"
        lc.GENESIS_BASELINE_PATH = Path(tmp) / "genesis_baseline.json"
        lc.STATE_DIR = Path(tmp)
        from tools.governance.t03_pipeline_state_manager import PipelineStateManager
        from tools.safety.t23_state_journal import StateJournal

        j = StateJournal(lc.WAL_PATH)
        t03 = PipelineStateManager(sp, j)
        ingested = t03.ingest_seed(LOOP_DIR / "pipeline_state.seed.json")
        if not ingested.get("master_plan"):
            failures.append("T03 ingest failed")
        windowed = ctx.horizon.select_window(ingested)
        if not (windowed.get("horizon") or {}).get("window"):
            failures.append("T05 select_window failed")

    # T06
    ctx.ast_mapper.build_map()
    if not ctx.ast_mapper.meta_summary():
        failures.append("T06 ast map empty")

    # T07
    rag = ctx.rag.initialize_at_genesis(full_if_missing=False)
    if not rag.ok and not lc.VECTORS_PATH.is_file():
        failures.append(f"T07 init: {rag.message}")

    # T08
    step = state["master_plan"][0]
    auth = ctx.boundary_compiler.compile_step(step, HERMES_ROOT)
    if not auth.boundaries:
        failures.append("T08 compile_step failed")

    # T09-T11 (gate only; spawn may fail on Windows bridge)
    gate = ctx.cursor_gate.run(skip=True)
    if gate.status.value != "CURSOR_UNAVAILABLE":
        failures.append("T11 skip gate unexpected")

    gate2 = ctx.cursor_gate.run(budget_ok=True)
    if not gate2.status.value:
        failures.append("T11 live gate empty status")

    # T12-T14
    targets = ["main orchestration loop/orchestrator/main.py"]
    comp = ctx.compiler.check_files(HERMES_ROOT, targets)
    if not comp.ok:
        failures.append(f"T12 compile: {comp.output[:200]}")
    sem = ctx.semantic.check("wrap", ctx.diff_analyzer.diff_summary(HERMES_ROOT, targets))
    if not sem.ok:
        failures.append(f"T13 semantic: {sem.raw[:200]}")
    diff = ctx.diff_analyzer.single_step_audit(HERMES_ROOT, auth.boundaries)
    if not diff.ok and diff.violations:
        failures.append(f"T14 audit: {diff.violations}")

    # T15
    snap = ctx.git_snapshot.take_snapshot(HERMES_ROOT, targets)
    if not snap:
        failures.append("T15 snapshot failed")

    # T16-T17
    os.environ["HERMES_IN_SESSION"] = "1"
    test = ctx.test_runner.run_tests(HERMES_ROOT)
    if not test.ok:
        failures.append(f"T16 tests exit {test.exit_code}")
    fuzz = ctx.fuzzer.run_against_schemas(LOOP_DIR / "docs" / "schemas")
    if not fuzz.ok:
        failures.append(f"T17 fuzzer: {fuzz.crashes}")

    # T18-T20
    norm = ctx.error_normalizer.normalize("TypeError: foo")
    triage = ctx.triage.classify(
        ctx.objective_envelope.wrap(locked, "triage", norm.signature),
        norm.signature,
    )
    if triage.classification not in {"CODE_BUG", "PLAN_OMISSION", "INFRA_EVENT"}:
        failures.append(f"T18 bad class: {triage.classification}")
    s, n = ctx.strike_breaker.record_strike(state, "f.py", norm.hash)
    if n < 1:
        failures.append("T20 strike failed")

    # T21
    if not ctx.budget.initialize(state).get("budget"):
        failures.append("T21 init failed")

    # T22
    ctx.cycle_detector.record_phase_transition(state, "P1", None)

    # T23
    from tools.safety.t23_state_journal import JournalEntry

    ctx.journal.append_wal(
        JournalEntry(
            timestamp=0,
            phase="P0",
            step_id=None,
            transition_type="TEST",
            payload={},
        )
    )

    # T24 synthesizer exists
    if not hasattr(ctx.tool_synthesizer, "synthesize"):
        failures.append("T24 missing synthesize")

    # T25-T27
    rej = ctx.registry.validate_tool_call("T09", Phase.P1, {})
    if rej is None:
        failures.append("T25 should block T09 in P1")
    val = ctx.tool_validator.validate("T07", {}, Phase.P0)
    if hasattr(val, "reason"):
        failures.append(f"T27 rejected T07 in P0: {val.reason}")

    # T28
    ctx.paralysis_breaker.apply_default(current_phase=Phase.P1, options=["a", "bb/cc"], state=state)

    # T29
    from orchestrator.contracts import register_all

    register_all(ctx.phase_controller)
    if not ctx.phase_controller.contracts:
        failures.append("T29 no contracts registered")

    # T30
    ctx.escalation.alert("smoke test", state, extra={"ok": True})

    if failures:
        print("[FAIL] Smoke failures:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("[OK] All 30 tools smoke-tested via bootstrap context")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
