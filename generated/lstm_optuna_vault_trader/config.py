"""Research pipeline configuration with orchestrator smoke defaults."""

from __future__ import annotations

import os

SMOKE = os.getenv("HERMES_RESEARCH_SMOKE", "1") == "1"

LIMIT_BARS = 2_000 if SMOKE else 50_000
N_SPLITS = 2 if SMOKE else 5
OPTUNA_TRIALS = 3 if SMOKE else 20
EPOCHS = 5 if SMOKE else 30
MIN_TRAIN_BARS = 120 if SMOKE else 800
TEST_BARS = 40 if SMOKE else 200
LOOKBACK = 30 if SMOKE else 60
