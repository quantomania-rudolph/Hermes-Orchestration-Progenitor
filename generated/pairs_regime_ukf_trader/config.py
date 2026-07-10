"""Research configuration for the pairs regime UKF trader pipeline."""

from __future__ import annotations

import os

SMOKE = os.getenv("HERMES_RESEARCH_SMOKE", "1") == "1"

LIMIT_BARS = 1200 if SMOKE else 50_000
UNIVERSE = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA"]
MAX_PAIRS = 3 if SMOKE else 20
UKF_SMOKE = int(os.getenv("UKF_SMOKE", "1" if SMOKE else "0")) == 1

# Pair discovery thresholds
PAIR_ROLLING_WINDOW = 60 if SMOKE else 120
PAIR_MIN_OVERLAP_BARS = 80 if SMOKE else 100
PAIR_MIN_ABS_CORR = 0.65
PAIR_MAX_COINT_P = 0.05
PAIR_SCORE_W_CORR = 0.4
PAIR_SCORE_W_COINT = 0.35
PAIR_SCORE_W_TAIL = 0.25
PAIR_TAIL_QUANTILE = 0.95

# Intel Core Ultra / Arc XPU (PyTorch torch.xpu)
USE_INTEL_XPU = os.getenv("HERMES_USE_INTEL_XPU", "auto").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
    "cpu",
}
FORCE_CPU = os.getenv("HERMES_FORCE_CPU", "0") == "1"

# Regime trading defaults (see ARCHITECTURE.md for detection rules)
REGIME_PARAMS = {
    "BULL": {
        "entry_z": 1.6,
        "exit_z": 0.4,
        "position_cap_frac": 1.0,
        "allow_new_entries": True,
        "require_copula_tail": False,
        "min_regime_confidence": 0.0,
    },
    "BEAR": {
        "entry_z": 2.0,
        "exit_z": 0.5,
        "position_cap_frac": 0.7,
        "allow_new_entries": True,
        "require_copula_tail": False,
        "min_regime_confidence": 0.0,
    },
    "VOLATILE": {
        "entry_z": 2.8,
        "exit_z": 0.8,
        "position_cap_frac": 0.5,
        "allow_new_entries": True,
        "require_copula_tail": True,
        "min_regime_confidence": 0.0,
    },
    "CRASH": {
        "entry_z": 3.5,
        "exit_z": 1.2,
        "position_cap_frac": 0.25,
        "allow_new_entries": True,
        "require_copula_tail": False,
        "min_regime_confidence": 0.7,
    },
}
