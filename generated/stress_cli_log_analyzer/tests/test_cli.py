"""Pytest checks for the NGINX access log CLI analyzer (fixture log only)."""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import pytest

_PKG = Path(__file__).resolve().parents[1]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

os.environ.setdefault("HERMES_LOG_ANALYZER_SMOKE", "1")

from cli import analyze_log, main
from config import DEFAULT_LOG_PATH


@pytest.fixture
def fixture_log_path() -> Path:
    path = Path(DEFAULT_LOG_PATH)
    assert path.is_file(), f"fixture access.log missing: {path}"
    return path


def test_analyze_sample_log_error_rate_finite_and_top_paths_non_empty(
    fixture_log_path: Path,
):
    summary = analyze_log(fixture_log_path)

    assert isinstance(summary, dict)
    assert "error_rate" in summary
    assert "top_paths" in summary
    assert "status_counts" in summary

    assert isinstance(summary["top_paths"], list)
    assert len(summary["top_paths"]) > 0

    for item in summary["top_paths"]:
        assert isinstance(item, dict)
        assert "path" in item
        assert "count" in item
        assert isinstance(item["count"], int)
        assert item["count"] > 0

    assert isinstance(summary["error_rate"], (int, float))
    assert math.isfinite(float(summary["error_rate"]))
    assert 0.0 <= float(summary["error_rate"]) <= 1.0


def test_cli_main_emits_json_summary(fixture_log_path: Path, capsys):
    exit_code = main(["analyze_log", str(fixture_log_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    summary = json.loads(captured.out)

    assert math.isfinite(float(summary["error_rate"]))
    assert isinstance(summary["top_paths"], list)
    assert len(summary["top_paths"]) > 0
    assert isinstance(summary["status_counts"], dict)
    assert len(summary["status_counts"]) > 0
