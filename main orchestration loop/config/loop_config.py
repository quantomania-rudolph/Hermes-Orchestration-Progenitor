"""Static configuration for the HERMES main orchestration loop."""

from __future__ import annotations

import os
from pathlib import Path

# Project roots
LOOP_DIR = Path(__file__).resolve().parents[1]
HERMES_ROOT = LOOP_DIR.parent
WORKSPACE_ROOT = Path(
    os.environ.get("HERMES_WORKSPACE_ROOT", str(HERMES_ROOT.parent))
).resolve()

# External project output (outside main orchestration loop/)
GENERATED_OUTPUT_ROOT = Path(
    os.environ.get("HERMES_GENERATED_ROOT", str(HERMES_ROOT / "generated"))
).resolve()

# State paths (Layer 1)
PIPELINE_STATE_PATH = LOOP_DIR / "pipeline_state.json"
STATE_DIR = LOOP_DIR / "state"
WAL_PATH = STATE_DIR / "wal.jsonl"
SNAPSHOTS_DIR = STATE_DIR / "snapshots"
GENESIS_BASELINE_PATH = STATE_DIR / "genesis_baseline.json"
LAST_GOOD_PLAN_PATH = SNAPSHOTS_DIR / "last_good_plan.json"
HORIZON_OPEN_PATH = SNAPSHOTS_DIR / "horizon_open.json"

# Docs / rubric
ARCHITECTURE_MD = LOOP_DIR / "architecture.md"
DOCS_DIR = LOOP_DIR / "docs"
SCHEMAS_DIR = DOCS_DIR / "schemas"

# Index integration (links to parent project build_index)
BUILD_INDEX_SCRIPT = HERMES_ROOT / "scripts" / "setup_index" / "build_index.py"
VECTORS_PATH = HERMES_ROOT / "codebase_vectors.json"
INDEX_CONSISTENCY_LOG = STATE_DIR / "index_consistency.jsonl"

# Runtime parameters (T21, T04)
TOKEN_CAP = int(os.environ.get("HERMES_TOKEN_CAP", "2000000"))
USD_CAP = float(os.environ.get("HERMES_USD_CAP", "5.00"))
FLOOR_TOKENS = int(os.environ.get("HERMES_FLOOR_TOKENS", "100000"))
FLOOR_USD = float(os.environ.get("HERMES_FLOOR_USD", "0.50"))
MAX_STEP_GROWTH_PCT = int(os.environ.get("HERMES_MAX_STEP_GROWTH_PCT", "25"))
THREE_STRIKES_CAP = int(os.environ.get("HERMES_THREE_STRIKES_CAP", "3"))
HORIZON_WINDOW_SIZE = int(os.environ.get("HERMES_HORIZON_WINDOW", "3"))

# Model / SDK pins
CURSOR_SDK_VERSION_PIN = os.environ.get("HERMES_CURSOR_SDK_PIN", "cursor-sdk>=0.1.0")
NOLLAMA_OPENAI_BASE_URL = os.environ.get(
    "NOLLAMA_OPENAI_BASE_URL", "http://localhost:8000/v1"
)
HERMES_CHAT_MODEL = os.environ.get("HERMES_CHAT_MODEL", "qwen3-14b-int4")
CURSOR_MODEL = os.environ.get("HERMES_CURSOR_MODEL", "composer-2.5")

# Execution modes (read dynamically — CLI flags set env before run)
def is_dry_run() -> bool:
    return os.environ.get("HERMES_DRY_RUN", "0").strip().lower() in {"1", "true", "yes"}


def is_skip_cursor() -> bool:
    return os.environ.get("HERMES_SKIP_CURSOR", "0").strip().lower() in {"1", "true", "yes"}


def t09_runtime() -> str:
    """T09 implementation runtime: auto (cursor then qwen), cursor, or qwen."""
    return os.environ.get("HERMES_T09_RUNTIME", "auto").strip().lower()


def cursor_runtime() -> str:
    """Cursor SDK runtime: local (default), cloud (needs git remote), or auto."""
    return os.environ.get("HERMES_CURSOR_RUNTIME", "local").strip().lower()

# Tool registry
TOOL_REGISTRY_SCHEMA = LOOP_DIR / "config" / "tool_registry_schema.json"
STATIC_TOOL_REGISTRY = LOOP_DIR / "config" / "static_tool_registry.json"
SYSTEM_TOOLS_DIR = LOOP_DIR / "system_tools"
SYSTEM_TOOLS_QUARANTINE = SYSTEM_TOOLS_DIR / "quarantine"
SYSTEM_TOOLS_ACTIVE = SYSTEM_TOOLS_DIR / "active"
SYNTHESIZED_REGISTRY = SYSTEM_TOOLS_DIR / "registry.json"
