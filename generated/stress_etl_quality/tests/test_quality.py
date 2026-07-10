"""Pytest quality checks for the stress_etl_quality fixture CSV."""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import pytest

_PKG = Path(__file__).resolve().parents[1]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

os.environ.setdefault("HERMES_ETL_SMOKE", "1")

from config import DEFAULT_CSV_PATH
from ingest import collect_validation_errors, load_csv
from quality import amount_iqr_outliers, duplicate_ids, null_rate, run_checks
from report import build_report


@pytest.fixture
def fixture_csv_path() -> Path:
    path = Path(DEFAULT_CSV_PATH)
    assert path.is_file(), f"fixture CSV missing: {path}"
    return path


@pytest.fixture
def fixture_df(fixture_csv_path: Path):
    return load_csv(fixture_csv_path)


def test_fixture_csv_validates(fixture_df):
    assert collect_validation_errors(fixture_df) == []


def test_fixture_passes_with_zero_critical_violations(fixture_csv_path: Path):
    report = build_report(csv_path=fixture_csv_path)
    checks = run_checks(csv_path=fixture_csv_path)

    assert report["critical_violations"] == 0
    assert report["passed"] is True
    assert math.isfinite(float(report["critical_violations"]))
    assert math.isfinite(float(report["total_violations"]))
    assert report["checks"] == checks
    assert checks["null_rate"] == 0
    assert checks["duplicate_ids"] == 0
    for name, count in checks.items():
        assert isinstance(count, int), f"{name} violation count must be int"
        assert count >= 0
        assert math.isfinite(float(count)), f"{name} violation count must be finite"


def test_fixture_metrics_are_finite(fixture_df):
    metrics = {
        "null_rate": null_rate(fixture_df),
        "duplicate_ids": duplicate_ids(fixture_df),
        "amount_iqr_outliers": amount_iqr_outliers(fixture_df),
    }

    assert metrics["null_rate"] == 0.0
    assert metrics["duplicate_ids"] == 0

    for name, value in metrics.items():
        assert isinstance(value, (int, float)), f"{name} must be numeric"
        assert math.isfinite(float(value)), f"{name} must be finite"
        assert float(value) >= 0, f"{name} must be non-negative"
        if name == "null_rate":
            assert float(value) <= 1.0, "null_rate must be a fraction"


def test_run_checks_violations_are_finite(fixture_csv_path: Path):
    checks = run_checks(csv_path=fixture_csv_path)

    assert set(checks) == {"null_rate", "duplicate_ids", "amount_iqr_outliers"}
    for name, count in checks.items():
        assert isinstance(count, int), f"{name} violation count must be int"
        assert count >= 0
        assert math.isfinite(float(count)), f"{name} violation count must be finite"
