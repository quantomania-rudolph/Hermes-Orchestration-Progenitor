#!/usr/bin/env bash
# Live Cursor-first pairs regime UKF trader (WSL2 + Intel Arc XPU). Logs to state/live_pairs_ukf_cursor.log
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WIN_HERMES="/mnt/c/Users/Rudol/Desktop/Hermes_Orchestration"
if [[ -d "$WIN_HERMES" ]]; then
  HERMES_ROOT="$WIN_HERMES"
fi
cd "$HERMES_ROOT"

PYTHON="python3"
if [[ -x "$HERMES_ROOT/.venv-wsl/bin/python" ]]; then
  PYTHON="$HERMES_ROOT/.venv-wsl/bin/python"
fi
export PATH="$HOME/.local/bin:$HERMES_ROOT/.venv-wsl/bin:$PATH"

if [[ -f "$HERMES_ROOT/.env.local" ]]; then
  set -a
  # shellcheck disable=SC1091
  source <(grep -v '^\s*#' "$HERMES_ROOT/.env.local" | grep -v '^\s*$' | sed 's/\r$//')
  set +a
fi

# shellcheck disable=SC1091
source "main orchestration loop/run/_wsl_nollama_url.sh"
if NOLLAMA_URL="$(wsl_resolve_nollama_url 2>/dev/null)"; then
  export NOLLAMA_OPENAI_BASE_URL="$NOLLAMA_URL"
  export NOLLAMA_HEALTH_URL="${NOLLAMA_URL%/v1}/health"
  echo "[env] NoLlama base: $NOLLAMA_OPENAI_BASE_URL"
else
  echo "[WARN] NoLlama not reachable from WSL — run NoLlama on Windows first"
fi

export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8
export HERMES_WORKSPACE_ROOT="$HERMES_ROOT"
export HERMES_T09_RUNTIME=cursor
export HERMES_CURSOR_SESSION_TIMEOUT_SEC="${HERMES_CURSOR_SESSION_TIMEOUT_SEC:-1200}"
export HERMES_CURSOR_RUNTIME=local
export HERMES_CURSOR_BACKEND=cli
export HERMES_REQUIRE_LIVE_CURSOR=1
export HERMES_SKIP_INDEX_REBUILD=1
export HERMES_SKIP_AST_REBUILD=1
export HERMES_RESEARCH_SMOKE=1
export HERMES_USE_INTEL_XPU="${HERMES_USE_INTEL_XPU:-auto}"
export HERMES_OUTPUT_SLUG=pairs_regime_ukf_trader
unset HERMES_DRY_RUN
unset HERMES_SKIP_CURSOR
unset HERMES_ALLOW_T24

SEED="main orchestration loop/pipeline_state.pairs_regime_ukf_trader.seed.json"
LOG="main orchestration loop/state/live_pairs_ukf_cursor.log"
STATE="main orchestration loop/pipeline_state.json"
OUT="generated/pairs_regime_ukf_trader"

echo "=== HERMES Live Pairs Regime UKF (WSL2 Cursor + Intel Arc) ===" | tee "$LOG"
echo "Time: $(date -Iseconds)" | tee -a "$LOG"
echo "T09=cursor | backend=cli | runtime=local | xpu=$HERMES_USE_INTEL_XPU" | tee -a "$LOG"

RESUME="${HERMES_RESUME:-1}"
mkdir -p "main orchestration loop/state"

if [[ "$RESUME" == "1" ]] && [[ -f "$STATE" ]]; then
  echo "[resume] Keeping pipeline_state.json and existing artifacts" | tee -a "$LOG"
else
  rm -f "$STATE"
  rm -rf "$OUT"
  echo "[clean] Fresh pairs_regime_ukf_trader run" | tee -a "$LOG"
fi

echo "[env] HERMES_CURSOR_BACKEND=cli (agent -p via WSL2)" | tee -a "$LOG"
if ! bash "main orchestration loop/run/_wsl_agent_probe.sh" 2>&1 | tee -a "$LOG"; then
  echo "[FAIL] WSL agent CLI preflight — run 05_setup_wsl_environment.bat" | tee -a "$LOG"
  exit 1
fi

MAIN_ARGS=(--seed "$SEED" --repo "$HERMES_ROOT")
if [[ "$RESUME" == "1" ]] && [[ -f "$STATE" ]]; then
  MAIN_ARGS+=(--resume)
fi
"$PYTHON" "main orchestration loop/orchestrator/main.py" "${MAIN_ARGS[@]}" 2>&1 | tee -a "$LOG"
RC=${PIPESTATUS[0]}
echo "[exit] orchestrator rc=$RC" | tee -a "$LOG"
exit "$RC"
