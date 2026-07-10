"""Held-out CLI probes (DAEDALUS R23)."""

from __future__ import annotations

import sys
from pathlib import Path

_PKG = Path(__file__).resolve().parents[1]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

from parser import parse_line


def test_heldout_parse_malformed_line():
    row = parse_line("not-a-valid-log-line")
    assert row is None or row.get("status") is None
