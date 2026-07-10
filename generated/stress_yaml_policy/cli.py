"""CLI for YAML policy validation and JSON report generation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

try:
    from config import DEFAULT_POLICY_PATH, REPORT_PATH
except ImportError:  # pragma: no cover - package import when run as module
    from .config import DEFAULT_POLICY_PATH, REPORT_PATH

try:
    from validator import ValidationResult, validate_policy
except ImportError:  # pragma: no cover - package import when run as module
    from .validator import ValidationResult, validate_policy

__all__ = ["write_validation_report", "main"]


def write_validation_report(
    *,
    yaml_path: str | Path | None = None,
    report_path: Path | str | None = None,
) -> ValidationResult:
    """Validate a policy YAML file and write ``reports/validation.json``."""
    path = Path(yaml_path) if yaml_path is not None else DEFAULT_POLICY_PATH
    result = validate_policy(path)
    out = Path(report_path) if report_path is not None else REPORT_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    """CLI entry: validate policy YAML, emit JSON report, exit 1 on violations."""
    parser = argparse.ArgumentParser(description="Validate a YAML policy document.")
    parser.add_argument(
        "yaml_path",
        nargs="?",
        default=str(DEFAULT_POLICY_PATH),
        help="Path to policy YAML (default: sample fixture)",
    )
    parser.add_argument(
        "--report-path",
        default=None,
        help=f"Path for validation.json report (default: {REPORT_PATH})",
    )
    args = parser.parse_args(argv)
    result = write_validation_report(
        yaml_path=args.yaml_path,
        report_path=args.report_path,
    )
    return 0 if result.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
