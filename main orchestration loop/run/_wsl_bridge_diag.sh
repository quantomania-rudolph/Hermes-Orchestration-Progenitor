#!/usr/bin/env bash
set -euo pipefail
HERMES_ROOT="/mnt/c/Users/Rudol/Desktop/Hermes_Orchestration"
export PATH="$HOME/.local/bin:$HERMES_ROOT/.venv-wsl/bin:$PATH"
cd "$HERMES_ROOT"
echo "=== bridge diag ==="
agent --version
BRIDGE="$HERMES_ROOT/.venv-wsl/lib/python3.12/site-packages/cursor_sdk/_vendor/bridge/bin/cursor-sdk-bridge"
for args in \
  "--workspace $HERMES_ROOT" \
  "--workspace $HERMES_ROOT --state-root /tmp/hermes-bridge-state" \
  "--workspace $HERMES_ROOT/generated/vault_lr_strategy --state-root /tmp/hermes-bridge-state"; do
  echo "Launching bridge (60s) with $args"
  # shellcheck disable=SC2086
  timeout 60 $BRIDGE $args 2>&1 | head -5 || true
  pkill -f cursor-sdk-bridge 2>/dev/null || true
  sleep 2
done
