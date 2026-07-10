#!/usr/bin/env bash
# Live NN stress test — same WSL CLI Cursor path as LR test.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WIN_HERMES="/mnt/c/Users/Rudol/Desktop/Hermes_Orchestration"
[[ -d "$WIN_HERMES" ]] && HERMES_ROOT="$WIN_HERMES"
cd "$HERMES_ROOT"
export PATH="$HOME/.local/bin:$HERMES_ROOT/.venv-wsl/bin:$PATH"
PYTHON="$HERMES_ROOT/.venv-wsl/bin/python"
export PYTHONUNBUFFERED=1 HERMES_WORKSPACE_ROOT="$HERMES_ROOT"
export HERMES_T09_RUNTIME=cursor HERMES_CURSOR_BACKEND=cli HERMES_CURSOR_RUNTIME=local
export HERMES_SKIP_INDEX_REBUILD=1 HERMES_CURSOR_SESSION_TIMEOUT_SEC="${HERMES_CURSOR_SESSION_TIMEOUT_SEC:-1200}"
unset HERMES_DRY_RUN HERMES_SKIP_CURSOR
SEED="main orchestration loop/pipeline_state.test_nn_trader.seed.json"
LOG="main orchestration loop/state/live_nn_cursor.log"
STATE="main orchestration loop/pipeline_state.json"
OUT="generated/nn_vault_trader"
echo "=== HERMES Live NN Cursor Stress Test ===" | tee "$LOG"
rm -f "$STATE" && rm -rf "$OUT"
bash "main orchestration loop/run/_wsl_agent_probe.sh" 2>&1 | tee -a "$LOG"
"$PYTHON" "main orchestration loop/orchestrator/main.py" --seed "$SEED" 2>&1 | tee -a "$LOG"
exit "${PIPESTATUS[0]}"
