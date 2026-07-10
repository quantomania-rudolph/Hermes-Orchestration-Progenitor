#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$HERMES_ROOT"
export HERMES_STRESS_ONLY=stress_fastapi_todo
export HERMES_SKIP_INDEX_REBUILD=1
export HERMES_SKIP_AST_REBUILD=1
export HERMES_SKIP_FINAL_TESTS=1
rm -f "main orchestration loop/pipeline_state.json"
rm -rf "generated/stress_fastapi_todo"
exec bash "main orchestration loop/run/13_run_stress_campaign.sh"
