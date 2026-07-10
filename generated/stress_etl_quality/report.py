"""Quality report generation for the transaction CSV ETL pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

try:
    from config import DEFAULT_CSV_PATH, REPORT_DIR, SMOKE
except ImportError:  # pragma: no cover - package import when run as module
    from .config import DEFAULT_CSV_PATH, REPORT_DIR, SMOKE

try:
    from quality import run_checks
except ImportError:  # pragma: no cover - package import when run as module
    from .quality import run_checks

__all__ = ["build_report", "write_reports", "main"]


def build_report(*, csv_path: str | Path | None = None) -> dict[str, Any]:
    """Assemble a quality report payload from ``quality.run_checks()``."""
    path = Path(csv_path) if csv_path is not None else DEFAULT_CSV_PATH
    checks = run_checks(csv_path=path)
    critical_violations = checks["null_rate"] + checks["duplicate_ids"]
    total_violations = sum(checks.values())

    return {
        "csv_path": str(path.resolve()),
        "smoke": SMOKE,
        "checks": checks,
        "critical_violations": critical_violations,
        "total_violations": total_violations,
        "passed": critical_violations == 0,
    }


def _render_markdown(report: dict[str, Any]) -> str:
    checks = report["checks"]
    lines = [
        "# CSV ETL Quality Report",
        "",
        "## Summary",
        "",
        f"- CSV: `{report['csv_path']}`",
        f"- Smoke mode: `{report['smoke']}`",
        f"- Critical violations: **{report['critical_violations']}**",
        f"- Total violations: **{report['total_violations']}**",
        f"- Passed: **{report['passed']}**",
        "",
        "## Quality checks",
        "",
        "| Check | Violations |",
        "|-------|------------|",
    ]
    for name, count in checks.items():
        lines.append(f"| {name} | {count} |")
    lines.append("")
    return "\n".join(lines) + "\n"


def write_reports(
    *,
    csv_path: str | Path | None = None,
    report_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Run quality checks and write ``quality_report.json`` and ``quality_report.md``."""
    report = build_report(csv_path=csv_path)
    out = Path(report_dir) if report_dir is not None else REPORT_DIR
    out.mkdir(parents=True, exist_ok=True)
    (out / "quality_report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    (out / "quality_report.md").write_text(_render_markdown(report), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    """CLI entry: generate quality reports for a transactions CSV."""
    parser = argparse.ArgumentParser(description="Generate CSV ETL quality reports.")
    parser.add_argument(
        "csv_path",
        nargs="?",
        default=str(DEFAULT_CSV_PATH),
        help="Path to transactions CSV (default: sample fixture)",
    )
    parser.add_argument(
        "--report-dir",
        default=None,
        help=f"Directory for quality_report.json and quality_report.md (default: {REPORT_DIR})",
    )
    args = parser.parse_args(argv)
    write_reports(csv_path=args.csv_path, report_dir=args.report_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
