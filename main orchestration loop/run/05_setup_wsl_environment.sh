#!/usr/bin/env bash
# One-shot WSL bootstrap: packages, Cursor CLI, cursor-sdk, HERMES smoke test.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WIN_HERMES="/mnt/c/Users/Rudol/Desktop/Hermes_Orchestration"
if [[ -d "$WIN_HERMES" ]]; then
  HERMES_ROOT="$WIN_HERMES"
fi

export DEBIAN_FRONTEND=noninteractive

echo "=== HERMES WSL Environment Setup ==="
echo "Distro: $(. /etc/os-release; echo "$PRETTY_NAME")"
echo "HERMES: $HERMES_ROOT"

echo "[1/6] Installing base packages..."
apt-get update -qq
apt-get install -y -qq curl ca-certificates python3 python3-pip python3-venv git

echo "[2/6] Installing Cursor Agent CLI..."
if ! command -v agent >/dev/null 2>&1; then
  if ! curl -fsSL --max-time 120 https://cursor.com/install -o /tmp/cursor_install.sh; then
    echo "[FAIL] Could not download https://cursor.com/install"
    echo "       Your network is likely intercepting HTTPS (Eero/router TLS)."
    echo "       Fix: phone hotspot OR disable HTTPS inspection, then re-run:"
    echo "         wsl -d Ubuntu-24.04 -u root -- bash $0"
    exit 1
  fi
  bash /tmp/cursor_install.sh
fi

if ! grep -q 'HOME/.local/bin' "$HOME/.bashrc" 2>/dev/null; then
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
fi
export PATH="$HOME/.local/bin:$PATH"

echo "[3/6] Verifying agent CLI..."
agent --version

echo "[4/6] Installing cursor-sdk for Python bridge..."
VENV="$HERMES_ROOT/.venv-wsl"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install "cursor-sdk>=0.1.0"
if [[ -f "$HERMES_ROOT/requirements-hermes.txt" ]]; then
  "$VENV/bin/pip" install -r "$HERMES_ROOT/requirements-hermes.txt"
fi
export PATH="$VENV/bin:$PATH"

echo "[5/6] Loading CURSOR_API_KEY from Windows .env.local..."
ENV_FILE="$HERMES_ROOT/.env.local"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1091
  source <(grep -v '^\s*#' "$ENV_FILE" | grep -v '^\s*$' | sed 's/\r$//')
  set +a
  if [[ -n "${CURSOR_API_KEY:-}" ]]; then
    echo "export CURSOR_API_KEY=\"$CURSOR_API_KEY\"" >> "$HOME/.bashrc"
    echo "[OK] CURSOR_API_KEY wired into ~/.bashrc"
  fi
else
  echo "[WARN] No .env.local at $ENV_FILE"
fi

echo "[6/6] Probing Cursor local bridge from WSL..."
cd "$HERMES_ROOT"
"$VENV/bin/python" - <<'PY'
import os, sys
sys.path.insert(0, "main orchestration loop")
from pathlib import Path
from hermes_secrets import load_local_env
load_local_env()
key = os.environ.get("CURSOR_API_KEY", "").strip()
if not key:
    print("[WARN] CURSOR_API_KEY not set")
    raise SystemExit(0)
from cursor_sdk import Agent, LocalAgentOptions
root = Path(".").resolve()
with Agent.create(
    api_key=key,
    model=os.environ.get("HERMES_CURSOR_MODEL", "composer-2.5"),
    local=LocalAgentOptions(cwd=str(root)),
):
    print("[OK] Cursor SDK local bridge works in WSL")
PY

echo
echo "=== WSL setup complete ==="
echo "Run HERMES trading test:"
echo "  bash \"$SCRIPT_DIR/05_run_wsl.sh\" live"
