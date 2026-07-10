#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$HERMES_ROOT"
export HERMES_SKIP_INDEX_REBUILD=1 HERMES_SKIP_AST_REBUILD=1
FAIL=0
for slug in stress_cli_log_analyzer stress_fastapi_todo; do
  echo "=== RETRY $slug ==="
  rm -f "main orchestration loop/pipeline_state.json"
  rm -rf "generated/${slug}"
  export HERMES_STRESS_ONLY="$slug"
  if ! bash "main orchestration loop/run/13_run_stress_campaign.sh"; then
    FAIL=$((FAIL + 1))
  fi
done
exit "$FAIL"
