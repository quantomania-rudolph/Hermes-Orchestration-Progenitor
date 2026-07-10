"""Wire all T01-T30 tools and shared services."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parents[1]
HERMES_ROOT = LOOP_DIR.parent
if str(LOOP_DIR) not in sys.path:
    sys.path.insert(0, str(LOOP_DIR))
if str(HERMES_ROOT) not in sys.path:
    sys.path.insert(0, str(HERMES_ROOT))

import config.loop_config as loop_config  # noqa: E402
from agents.cursor_sdk import CursorSDK  # noqa: E402
from tools.agents.t09_agent_creator import AgentCreator  # noqa: E402
from tools.agents.t10_agent_reviewer import AgentReviewer  # noqa: E402
from tools.agents.t11_cursor_gate import CursorAvailabilityGate  # noqa: E402
from tools.context.index_bridge import IndexBridge  # noqa: E402
from tools.context.t06_ast_mapper import ASTMapper  # noqa: E402
from tools.context.t07_rag_provisioner import RAGProvisioner  # noqa: E402
from tools.context.t08_scope_boundary_compiler import ScopeBoundaryCompiler  # noqa: E402
from tools.governance.t01_objective_envelope import ObjectiveEnvelope  # noqa: E402
from tools.governance.t02_objective_hash import ObjectiveHashVerifier  # noqa: E402
from tools.governance.t03_pipeline_state_manager import PipelineStateManager  # noqa: E402
from tools.governance.t04_plan_mutation_guard import PlanMutationGuard  # noqa: E402
from tools.governance.t05_horizon_controller import HorizonWindowController  # noqa: E402
from tools.meta.t24_tool_synthesizer import ToolSynthesizer  # noqa: E402
from tools.meta.t25_tool_registry import ToolRegistry  # noqa: E402
from tools.orchestration.t26_model_router import ModelRouter  # noqa: E402
from tools.orchestration.t27_tool_call_validator import ToolCallValidator  # noqa: E402
from tools.orchestration.t28_paralysis_breaker import ParalysisBreaker  # noqa: E402
from tools.orchestration.t29_phase_controller import PhaseTransitionController  # noqa: E402
from tools.orchestration.t30_human_escalation import HumanEscalation  # noqa: E402
from tools.safety.t20_strike_breaker import StrikeBreaker  # noqa: E402
from tools.safety.t21_budget_accountant import BudgetAccountant, BudgetConfig  # noqa: E402
from tools.safety.t22_cycle_detector import CycleDetector  # noqa: E402
from tools.safety.t23_state_journal import StateJournal  # noqa: E402
from tools.verification.t12_compiler_check import CompilerCheck  # noqa: E402
from tools.verification.t13_semantic_checker import SemanticChecker  # noqa: E402
from tools.verification.t14_diff_analyzer import DiffAnalyzer  # noqa: E402
from tools.verification.t15_git_snapshot import GitSnapshot  # noqa: E402
from tools.verification.t16_test_runner import TestRunner  # noqa: E402
from tools.verification.t17_fuzzer import DataFuzzer  # noqa: E402
from tools.verification.t18_triage_classifier import FailureTriageClassifier  # noqa: E402
from tools.verification.t19_error_normalizer import ErrorNormalizer  # noqa: E402


@dataclass
class HermesContext:
    loop_dir: Path
    hermes_root: Path
    repo_root: Path
    state_manager: PipelineStateManager
    journal: StateJournal
    objective_verifier: ObjectiveHashVerifier
    objective_envelope: ObjectiveEnvelope
    mutation_guard: PlanMutationGuard
    horizon: HorizonWindowController
    budget: BudgetAccountant
    index_bridge: IndexBridge
    rag: RAGProvisioner
    ast_mapper: ASTMapper
    boundary_compiler: ScopeBoundaryCompiler
    registry: ToolRegistry
    tool_validator: ToolCallValidator
    phase_controller: PhaseTransitionController
    cursor_gate: CursorAvailabilityGate
    cursor_sdk: CursorSDK
    agent_creator: AgentCreator
    agent_reviewer: AgentReviewer
    compiler: CompilerCheck
    semantic: SemanticChecker
    diff_analyzer: DiffAnalyzer
    git_snapshot: GitSnapshot
    test_runner: TestRunner
    fuzzer: DataFuzzer
    triage: FailureTriageClassifier
    error_normalizer: ErrorNormalizer
    strike_breaker: StrikeBreaker
    cycle_detector: CycleDetector
    tool_synthesizer: ToolSynthesizer
    model_router: ModelRouter
    paralysis_breaker: ParalysisBreaker
    escalation: HumanEscalation


def build_context(repo_root: Path | None = None) -> HermesContext:
    loop_config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    root = repo_root or loop_config.HERMES_ROOT
    journal = StateJournal(loop_config.WAL_PATH)
    state_manager = PipelineStateManager(loop_config.PIPELINE_STATE_PATH, journal)
    sdk = CursorSDK()
    return HermesContext(
        loop_dir=LOOP_DIR,
        hermes_root=loop_config.HERMES_ROOT,
        repo_root=root,
        state_manager=state_manager,
        journal=journal,
        objective_verifier=ObjectiveHashVerifier(),
        objective_envelope=ObjectiveEnvelope(ObjectiveHashVerifier()),
        mutation_guard=PlanMutationGuard(
            loop_config.GENESIS_BASELINE_PATH, loop_config.LAST_GOOD_PLAN_PATH
        ),
        horizon=HorizonWindowController(
            loop_config.HORIZON_WINDOW_SIZE,
            loop_config.HORIZON_OPEN_PATH,
            PlanMutationGuard(
                loop_config.GENESIS_BASELINE_PATH, loop_config.LAST_GOOD_PLAN_PATH
            ),
        ),
        budget=BudgetAccountant(
            BudgetConfig(
                token_cap=loop_config.TOKEN_CAP,
                usd_cap=loop_config.USD_CAP,
                floor_tokens=loop_config.FLOOR_TOKENS,
                floor_usd=loop_config.FLOOR_USD,
            )
        ),
        index_bridge=IndexBridge(
            build_script=loop_config.BUILD_INDEX_SCRIPT,
            vectors_path=loop_config.VECTORS_PATH,
            hermes_root=loop_config.HERMES_ROOT,
            consistency_log=loop_config.INDEX_CONSISTENCY_LOG,
        ),
        rag=RAGProvisioner(
            IndexBridge(
                build_script=loop_config.BUILD_INDEX_SCRIPT,
                vectors_path=loop_config.VECTORS_PATH,
                hermes_root=loop_config.HERMES_ROOT,
                consistency_log=loop_config.INDEX_CONSISTENCY_LOG,
            ),
            loop_config.DOCS_DIR,
            loop_config.HERMES_ROOT,
        ),
        ast_mapper=ASTMapper(root, loop_config.STATE_DIR / "ast_map.json"),
        boundary_compiler=ScopeBoundaryCompiler(),
        registry=ToolRegistry(
            loop_config.STATIC_TOOL_REGISTRY, loop_config.SYNTHESIZED_REGISTRY
        ),
        tool_validator=ToolCallValidator(
            ToolRegistry(loop_config.STATIC_TOOL_REGISTRY, loop_config.SYNTHESIZED_REGISTRY)
        ),
        phase_controller=PhaseTransitionController(),
        cursor_gate=CursorAvailabilityGate(),
        cursor_sdk=sdk,
        agent_creator=AgentCreator(sdk),
        agent_reviewer=AgentReviewer(sdk),
        compiler=CompilerCheck(),
        semantic=SemanticChecker(loop_config.ARCHITECTURE_MD),
        diff_analyzer=DiffAnalyzer(),
        git_snapshot=GitSnapshot(loop_config.STATE_DIR / "file_snapshots"),
        test_runner=TestRunner(),
        fuzzer=DataFuzzer(),
        triage=FailureTriageClassifier(),
        error_normalizer=ErrorNormalizer(),
        strike_breaker=StrikeBreaker(),
        cycle_detector=CycleDetector(),
        tool_synthesizer=ToolSynthesizer(
            sdk,
            loop_config.SYSTEM_TOOLS_QUARANTINE,
            loop_config.SYSTEM_TOOLS_ACTIVE,
            loop_config.SYNTHESIZED_REGISTRY,
        ),
        model_router=ModelRouter(),
        paralysis_breaker=ParalysisBreaker(),
        escalation=HumanEscalation(loop_config.STATE_DIR / "alerts"),
    )
