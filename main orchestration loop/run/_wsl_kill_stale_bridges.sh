#!/usr/bin/env bash
# Stop leftover cursor-sdk-bridge processes that block discovery on /mnt/c workspaces.
set -euo pipefail
pkill -f "cursor-sdk-bridge" 2>/dev/null || true
pkill -f "cursor_sdk/_vendor/bridge" 2>/dev/null || true
sleep 1
