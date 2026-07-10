"""Held-out ETL quality probes (DAEDALUS R23)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_PKG = Path(__file__).resolve().parents[1]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

from quality import null_rate


def test_heldout_null_rate_empty_frame():
    df = pd.DataFrame({"a": []})
    assert null_rate(df) == 0.0
