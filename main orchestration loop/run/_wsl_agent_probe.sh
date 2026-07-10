#!/usr/bin/env bash
set -euo pipefail
HERMES_ROOT="/mnt/c/Users/Rudol/Desktop/Hermes_Orchestration"
export PATH="$HOME/.local/bin:$PATH"
cd "$HERMES_ROOT"
if [[ -f "$HERMES_ROOT/.env.local" ]]; then
  set -a
  # shellcheck disable=SC1091
  key_line="$(grep -E '^\s*CURSOR_API_KEY=' "$HERMES_ROOT/.env.local" | tail -1 | sed 's/\r$//')"
  if [[ -n "$key_line" ]]; then
    export "$key_line"
  fi
  set +a
fi
MODEL="${HERMES_CURSOR_AGENT_MODEL:-${HERMES_CURSOR_MODEL:-auto}}"
agent -p --trust --model "$MODEL" "Reply with exactly: WSL_AGENT_OK"
