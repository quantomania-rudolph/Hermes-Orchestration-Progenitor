#!/usr/bin/env bash
# Re-run the three stress seeds that failed in the last campaign.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WIN_HERMES="/mnt/c/Users/Rudol/Desktop/Hermes_Orchestration"
[[ -d "$WIN_HERMES" ]] && HERMES_ROOT="$WIN_HERMES"
cd "$HERMES_ROOT"

export HERMES_SKIP_INDEX_REBUILD=1
export HERMES_SKIP_AST_REBUILD=1
export PYTHONUNBUFFERED=1

RESULTS="main orchestration loop/state/stress_retry_results.json"
echo "[]" > "$RESULTS"
FAILURES=0

for slug in stress_yaml_policy stress_cli_log_analyzer stress_fastapi_todo; do
  echo ""
  echo "=== RETRY slug=$slug ==="
  export HERMES_STRESS_ONLY="$slug"
  if ! bash "main orchestration loop/run/13_run_stress_campaign.sh"; then
    FAILURES=$((FAILURES + 1))
  fi
done

echo ""
echo "=== Retry complete failures=$FAILURES ==="
exit "$FAILURES"
