"""Pytest checks for the YAML policy validator CLI."""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

import pytest
import yaml

_PKG = Path(__file__).resolve().parents[1]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

os.environ["HERMES_POLICY_SMOKE"] = "1"

from cli import main, write_validation_report  # noqa: E402
from config import DEFAULT_POLICY_PATH  # noqa: E402
from schema import Severity  # noqa: E402
from validator import validate_policy  # noqa: E402


@pytest.fixture
def fixture_policy_path() -> Path:
    path = Path(DEFAULT_POLICY_PATH)
    assert path.is_file(), f"fixture policy missing: {path}"
    return path


@pytest.fixture
def fixture_policy_data(fixture_policy_path: Path) -> dict:
    data = yaml.safe_load(fixture_policy_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_good_fixture_passes(fixture_policy_path: Path) -> None:
    result = validate_policy(fixture_policy_path)

    assert result.valid is True
    assert result.violation_count == 0
    assert result.version == "1.0"
    assert result.rule_count == 5
    assert result.violations == []


def test_good_fixture_severity_enum_coverage(fixture_policy_data: dict) -> None:
    severities = {rule["severity"] for rule in fixture_policy_data["rules"]}
    expected = {level.value for level in Severity}
    assert severities == expected


def test_injected_bad_severity_fails(
    tmp_path: Path, fixture_policy_data: dict
) -> None:
    data = copy.deepcopy(fixture_policy_data)
    data["rules"][0]["severity"] = "urgent"

    bad_path = tmp_path / "bad_severity.yaml"
    bad_path.write_text(yaml.dump(data, sort_keys=False), encoding="utf-8")
    result = validate_policy(bad_path)

    assert result.valid is False
    assert result.violation_count >= 1
    assert result.rule_count == len(fixture_policy_data["rules"])
    assert any(v.code == "schema_error" for v in result.violations)
    assert any("severity" in v.message.lower() for v in result.violations)


def test_injected_duplicate_id_fails(
    tmp_path: Path, fixture_policy_data: dict
) -> None:
    data = copy.deepcopy(fixture_policy_data)
    duplicate_id = data["rules"][0]["id"]
    data["rules"][1]["id"] = duplicate_id

    bad_path = tmp_path / "duplicate_id.yaml"
    bad_path.write_text(yaml.dump(data, sort_keys=False), encoding="utf-8")
    result = validate_policy(bad_path)

    assert result.valid is False
    assert result.violation_count >= 1
    assert any(v.code == "duplicate_id" for v in result.violations)
    assert any(v.rule_id == duplicate_id for v in result.violations)


def test_validation_json_report(
    tmp_path: Path, fixture_policy_path: Path
) -> None:
    report_path = tmp_path / "validation.json"
    result = write_validation_report(
        yaml_path=fixture_policy_path,
        report_path=report_path,
    )

    assert result.valid is True
    assert report_path.is_file()

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["valid"] is True
    assert payload["version"] == "1.0"
    assert payload["rule_count"] == 5
    assert payload["violation_count"] == 0
    assert payload["violations"] == []
    assert payload["yaml_path"] == str(fixture_policy_path.resolve())


def test_cli_exit_code_good_fixture(
    tmp_path: Path, fixture_policy_path: Path
) -> None:
    report_path = tmp_path / "validation.json"
    code = main([str(fixture_policy_path), "--report-path", str(report_path)])

    assert code == 0
    assert json.loads(report_path.read_text(encoding="utf-8"))["valid"] is True


def test_cli_exit_code_bad_severity(
    tmp_path: Path, fixture_policy_data: dict
) -> None:
    data = copy.deepcopy(fixture_policy_data)
    data["rules"][0]["severity"] = "invalid"
    bad_path = tmp_path / "bad_severity_cli.yaml"
    bad_path.write_text(yaml.dump(data, sort_keys=False), encoding="utf-8")
    report_path = tmp_path / "validation.json"

    code = main([str(bad_path), "--report-path", str(report_path)])

    assert code == 1
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["valid"] is False
    assert payload["violation_count"] >= 1
    assert any(v["code"] == "schema_error" for v in payload["violations"])
