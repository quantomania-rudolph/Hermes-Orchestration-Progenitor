"""Aggregate parsed NGINX access log entries into summary statistics."""

from __future__ import annotations

from collections import Counter

try:
    from config import ERROR_STATUS_MIN, TOP_N_PATHS
except ImportError:  # pragma: no cover - package import when run as module
    from .config import ERROR_STATUS_MIN, TOP_N_PATHS

__all__ = ["summarize"]


def summarize(
    entries: list[dict],
    *,
    top_n: int | None = None,
) -> dict:
    """Summarize parsed log entries into status histogram, top paths, and totals."""
    limit = TOP_N_PATHS if top_n is None else top_n

    status_counter: Counter[int] = Counter()
    path_counter: Counter[str] = Counter()
    total_bytes = 0
    error_count = 0

    for entry in entries:
        status = int(entry["status"])
        path = str(entry["path"])
        nbytes = int(entry["bytes"])

        status_counter[status] += 1
        path_counter[path] += 1
        total_bytes += nbytes
        if status >= ERROR_STATUS_MIN:
            error_count += 1

    total = len(entries)
    error_rate = error_count / total if total else 0.0

    top_paths = [
        {"path": path, "count": count}
        for path, count in path_counter.most_common(limit)
    ]

    return {
        "status_counts": dict(status_counter),
        "top_paths": top_paths,
        "error_rate": error_rate,
        "total_bytes": total_bytes,
    }
