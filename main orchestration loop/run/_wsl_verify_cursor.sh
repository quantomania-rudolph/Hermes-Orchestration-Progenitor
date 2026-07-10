#!/usr/bin/env bash
set -euo pipefail
HERMES_ROOT="/mnt/c/Users/Rudol/Desktop/Hermes_Orchestration"
export PATH="$HOME/.local/bin:$HERMES_ROOT/.venv-wsl/bin:$PATH"
cd "$HERMES_ROOT"
if [[ -f "$HERMES_ROOT/.env.local" ]]; then
  set -a
  # shellcheck disable=SC1091
  source <(grep -v '^\s*#' "$HERMES_ROOT/.env.local" | grep -v '^\s*$' | sed 's/\r$//')
  set +a
fi
if [[ -z "${CURSOR_SDK_BRIDGE_URL:-}" ]]; then
  bash "main orchestration loop/run/_wsl_kill_stale_bridges.sh"
fi
exec "$HERMES_ROOT/.venv-wsl/bin/python" "main orchestration loop/verification/verify_wsl_cursor.py" "$@"
