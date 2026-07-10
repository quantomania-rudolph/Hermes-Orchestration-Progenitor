#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$HERMES_ROOT/generated/vault_lr_strategy"
PYTHON="$HERMES_ROOT/.venv-wsl/bin/python"
exec "$PYTHON" -c "
from backtest_pnl import run_backtest, write_reports
m = run_backtest()
write_reports(m)
print('METRICS:', m)
"
