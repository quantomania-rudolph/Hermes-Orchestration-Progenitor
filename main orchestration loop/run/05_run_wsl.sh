#!/usr/bin/env bash
# Run HERMES trading test from WSL2 (local Cursor bridge — avoids WinError 10038).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$HERMES_ROOT"

export HERMES_WORKSPACE_ROOT="$HERMES_ROOT"
export HERMES_T09_RUNTIME="${HERMES_T09_RUNTIME:-cursor}"
export HERMES_CURSOR_RUNTIME="${HERMES_CURSOR_RUNTIME:-local}"
export HERMES_DRY_RUN="${HERMES_DRY_RUN:-}"
export HERMES_SKIP_CURSOR="${HERMES_SKIP_CURSOR:-}"

# Load Windows-side secrets if present
if [[ -f "$HERMES_ROOT/.env.local" ]]; then
  set -a
  # shellcheck disable=SC1091
  source <(grep -v '^\s*#' "$HERMES_ROOT/.env.local" | grep -v '^\s*$' | sed 's/\r$//')
  set +a
fi

echo "=== HERMES WSL2 Run ==="
echo "Root: $HERMES_ROOT"
echo "T09:  $HERMES_T09_RUNTIME | Cursor runtime: $HERMES_CURSOR_RUNTIME"
echo

if ! python3 -c "import cursor_sdk" 2>/dev/null; then
  echo "[INFO] Installing cursor-sdk in WSL..."
  pip3 install --user "cursor-sdk>=0.1.0"
fi

MODE="${1:-dry}"
SEED="main orchestration loop/pipeline_state.test_trading.seed.json"

if [[ "$MODE" == "live" ]]; then
  unset HERMES_DRY_RUN
  unset HERMES_SKIP_CURSOR
  python3 "main orchestration loop/orchestrator/main.py" --seed "$SEED"
else
  export HERMES_DRY_RUN=1
  export HERMES_SKIP_CURSOR=1
  python3 "main orchestration loop/orchestrator/main.py" --seed "$SEED" --dry-run
fi
