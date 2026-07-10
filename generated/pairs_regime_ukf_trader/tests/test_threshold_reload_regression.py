"""Regression: CRASH entry gate survives run_pipeline module reloads."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_PKG = Path(__file__).resolve().parents[1]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

os.environ.setdefault("HERMES_RESEARCH_SMOKE", "1")

from run_pipeline import run_pipeline
from threshold_modulator import modulate


def test_crash_block_entry_survives_pipeline_reload():
    """run_pipeline reloads regime_markov; CRASH gate must still block low confidence."""
    row = {"regime_label": "CRASH", "regime_confidence": 0.5}
    assert modulate(2.0, row)["block_entry"] is True

    run_pipeline(smoke=True)

    out = modulate(2.0, row)
    assert out["block_entry"] is True, (
        "CRASH low-confidence block_entry must hold after run_pipeline reloads regime_markov"
    )
