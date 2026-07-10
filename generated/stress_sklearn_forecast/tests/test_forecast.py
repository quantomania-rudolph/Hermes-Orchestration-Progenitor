"""Pytest checks for the sklearn walk-forward forecast pipeline (CSV fixture only)."""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

_PKG = Path(__file__).resolve().parents[1]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

os.environ.setdefault("HERMES_FORECAST_SMOKE", "1")

pytest.importorskip("sklearn")

from backtest import run_backtest
from config import DEFAULT_CSV_PATH, MIN_TRAIN_ROWS, TEST_ROWS
from features import assert_no_leakage, build_features


@pytest.fixture
def fixture_csv_path() -> Path:
    path = Path(DEFAULT_CSV_PATH)
    assert path.is_file(), f"fixture CSV missing: {path}"
    return path


@pytest.fixture
def fixture_df(fixture_csv_path: Path) -> pd.DataFrame:
    return pd.read_csv(fixture_csv_path)


def test_leakage_assert_passes(fixture_df: pd.DataFrame):
    feature_df = build_features(fixture_df)
    assert len(feature_df) >= MIN_TRAIN_ROWS + TEST_ROWS
    assert_no_leakage(feature_df)


def test_backtest_oos_rows_positive_and_mae_finite(
    fixture_csv_path: Path, tmp_path: Path
):
    report_path = tmp_path / "metrics.json"
    metrics = run_backtest(
        csv_path=fixture_csv_path,
        report_path=report_path,
        write=True,
    )

    assert metrics["oos_rows"] > 0
    assert isinstance(metrics["mae"], (int, float))
    assert math.isfinite(float(metrics["mae"]))
    assert float(metrics["mae"]) >= 0.0
    assert isinstance(metrics["rmse"], (int, float))
    assert math.isfinite(float(metrics["rmse"]))
    assert float(metrics["rmse"]) >= 0.0

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload == metrics
    assert set(payload) == {"mae", "rmse", "oos_rows"}
    assert payload["oos_rows"] > 0
    assert math.isfinite(float(payload["mae"]))
    assert math.isfinite(float(payload["rmse"]))
