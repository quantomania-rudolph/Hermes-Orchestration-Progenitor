"""Smoke tests for leakage audit config."""

from config import ALL_DATASET_TAGS, SMOKE, MIN_BARS


def test_smoke_defaults():
    assert SMOKE is True
    assert len(ALL_DATASET_TAGS) == 4
    assert MIN_BARS > 0
