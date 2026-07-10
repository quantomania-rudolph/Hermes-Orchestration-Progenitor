#!/usr/bin/env bash
# Five sequential live Cursor stress runs — orchestrator capability campaign.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WIN_HERMES="/mnt/c/Users/Rudol/Desktop/Hermes_Orchestration"
[[ -d "$WIN_HERMES" ]] && HERMES_ROOT="$WIN_HERMES"
cd "$HERMES_ROOT"

PYTHON="python3"
[[ -x "$HERMES_ROOT/.venv-wsl/bin/python" ]] && PYTHON="$HERMES_ROOT/.venv-wsl/bin/python"
export PATH="$HOME/.local/bin:$HERMES_ROOT/.venv-wsl/bin:$PATH"

if [[ -f "$HERMES_ROOT/.env.local" ]]; then
  set -a
  # shellcheck disable=SC1091
  source <(grep -v '^\s*#' "$HERMES_ROOT/.env.local" | grep -v '^\s*$' | sed 's/\r$//')
  set +a
fi

# shellcheck disable=SC1091
source "main orchestration loop/run/_wsl_nollama_url.sh" || true
if NOLLAMA_URL="$(wsl_resolve_nollama_url 2>/dev/null)"; then
  export NOLLAMA_OPENAI_BASE_URL="$NOLLAMA_URL"
else
  export HERMES_SKIP_HERMES_BRAIN=1
  echo "[WARN] NoLlama unreachable — HERMES_SKIP_HERMES_BRAIN=1 (identity plans only)"
fi

export PYTHONUNBUFFERED=1
export HERMES_WORKSPACE_ROOT="$HERMES_ROOT"
export HERMES_T09_RUNTIME=cursor
export HERMES_CURSOR_BACKEND=cli
export HERMES_CURSOR_RUNTIME=local
export HERMES_SKIP_INDEX_REBUILD=1
export HERMES_SKIP_AST_REBUILD=1
unset HERMES_DRY_RUN HERMES_SKIP_CURSOR HERMES_ALLOW_T24

CAMPAIGN_LOG="main orchestration loop/state/stress_campaign.log"
RESULTS_JSON="main orchestration loop/state/stress_campaign_results.json"
mkdir -p "main orchestration loop/state"

# Order: smallest / fastest first
SEEDS=(
  "pipeline_state.test_stress_yaml_policy.seed.json"
  "pipeline_state.test_stress_cli_log_analyzer.seed.json"
  "pipeline_state.test_stress_etl_quality.seed.json"
  "pipeline_state.test_stress_sklearn_forecast.seed.json"
  "pipeline_state.test_stress_fastapi_todo.seed.json"
)

START_IDX="${HERMES_STRESS_START:-0}"
END_IDX="${HERMES_STRESS_END:-4}"
ONLY="${HERMES_STRESS_ONLY:-}"

echo "=== HERMES Stress Campaign ===" | tee "$CAMPAIGN_LOG"
echo "Time: $(date -Iseconds)" | tee -a "$CAMPAIGN_LOG"

if ! bash "main orchestration loop/run/_wsl_agent_probe.sh" 2>&1 | tee -a "$CAMPAIGN_LOG"; then
  echo "[FAIL] WSL agent CLI preflight" | tee -a "$CAMPAIGN_LOG"
  exit 1
fi

echo "[]" > "$RESULTS_JSON"
FAILURES=0

for i in "${!SEEDS[@]}"; do
  if (( i < START_IDX || i > END_IDX )); then
    continue
  fi
  SEED_FILE="main orchestration loop/${SEEDS[$i]}"
  SLUG="$("$PYTHON" -c "import json; d=json.load(open('$SEED_FILE')); print(d['genesis_baseline']['output_slug'])")"
  if [[ -n "$ONLY" && "$SLUG" != "$ONLY" ]]; then
    continue
  fi

  echo "" | tee -a "$CAMPAIGN_LOG"
  echo "=== RUN $((i+1))/${#SEEDS[@]} slug=$SLUG seed=$SEED_FILE ===" | tee -a "$CAMPAIGN_LOG"
  RUN_LOG="main orchestration loop/state/stress_${SLUG}.log"

  rm -f "main orchestration loop/pipeline_state.json"
  rm -rf "generated/${SLUG}"
  export HERMES_OUTPUT_SLUG="$SLUG"

  set +e
  "$PYTHON" "main orchestration loop/orchestrator/main.py" --seed "$SEED_FILE" 2>&1 | tee "$RUN_LOG"
  RC=${PIPESTATUS[0]}
  set -e

  echo "=== $SLUG exit=$RC ===" | tee -a "$CAMPAIGN_LOG"
  "$PYTHON" "main orchestration loop/verification/record_stress_run.py" \
    --slug "$SLUG" --seed "$SEED_FILE" --rc "$RC" --log "$RUN_LOG" \
    --results "$RESULTS_JSON" || true

  if [[ "$RC" -ne 0 ]]; then
    FAILURES=$((FAILURES + 1))
    echo "[WARN] $SLUG failed — continuing campaign" | tee -a "$CAMPAIGN_LOG"
  fi
done

echo "" | tee -a "$CAMPAIGN_LOG"
echo "=== Campaign complete failures=$FAILURES ===" | tee -a "$CAMPAIGN_LOG"
"$PYTHON" "main orchestration loop/verification/verify_stress_campaign.py" --results "$RESULTS_JSON" || true
exit "$FAILURES"
