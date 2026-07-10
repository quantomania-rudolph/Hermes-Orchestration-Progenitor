"""Held-out policy validation (DAEDALUS R23)."""

from __future__ import annotations

import sys
from pathlib import Path

_PKG = Path(__file__).resolve().parents[1]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

from schema import PolicyDocument


def test_heldout_empty_rules_document():
    doc = PolicyDocument(version="1.0", rules=[])
    assert doc.version == "1.0"
    assert len(doc.rules) == 0
