"""CLI for NGINX access log analysis and JSON summary output."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

try:
    from analyzer import summarize
except ImportError:  # pragma: no cover - package import when run as module
    from .analyzer import summarize

try:
    from config import DEFAULT_LOG_PATH, MAX_LINES
except ImportError:  # pragma: no cover - package import when run as module
    from .config import DEFAULT_LOG_PATH, MAX_LINES

try:
    from parser import parse_line
except ImportError:  # pragma: no cover - package import when run as module
    from .parser import parse_line

__all__ = ["analyze_log", "main"]


def analyze_log(log_path: str | Path | None = None) -> dict:
    """Parse an access log file and return a JSON-serializable summary dict."""
    path = Path(log_path) if log_path is not None else DEFAULT_LOG_PATH
    entries: list[dict] = []

    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle):
            if line_no >= MAX_LINES:
                break
            entry = parse_line(line)
            if entry is not None:
                entries.append(entry)

    return summarize(entries)


def main(argv: list[str] | None = None) -> int:
    """CLI entry: analyze_log path; print JSON summary; exit 0 on success."""
    parser = argparse.ArgumentParser(description="Analyze NGINX combined access logs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser(
        "analyze_log",
        help="Parse a log file and emit status histogram and top paths as JSON.",
    )
    analyze_parser.add_argument(
        "path",
        nargs="?",
        default=str(DEFAULT_LOG_PATH),
        help="Path to nginx access.log (default: sample fixture)",
    )

    args = parser.parse_args(argv)

    if args.command != "analyze_log":
        return 1

    summary = analyze_log(args.path)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
