"""Data quality checks for transaction CSV DataFrames."""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

try:
    from config import DEFAULT_CSV_PATH, IQR_MULTIPLIER, MAX_DUPLICATE_IDS, MAX_NULL_RATE
except ImportError:  # pragma: no cover - package import when run as module
    from .config import DEFAULT_CSV_PATH, IQR_MULTIPLIER, MAX_DUPLICATE_IDS, MAX_NULL_RATE

try:
    from ingest import load_csv
except ImportError:  # pragma: no cover - package import when run as module
    from .ingest import load_csv

__all__ = [
    "amount_iqr_outliers",
    "duplicate_ids",
    "null_rate",
    "run_checks",
]

_COLUMNS = ("id", "amount", "category", "timestamp")
_NULL_TOKENS = frozenset({"", "null", "none", "nan"})


def _is_null(value: object) -> bool:
    # pd.isna covers None, NaN, NaT, and pd.NA; keep explicit string tokens.
    try:
        if pd.isna(value):
            return True
    except TypeError:
        pass
    if isinstance(value, float) and not math.isfinite(value):
        return True
    if isinstance(value, str) and value.strip().lower() in _NULL_TOKENS:
        return True
    return False


def _null_cell_counts(df: pd.DataFrame) -> tuple[int, int]:
    """Return (null_count, total_cells) across expected columns."""
    if df.empty:
        return 0, 0

    null_count = 0
    total = 0
    for column in _COLUMNS:
        series = df[column] if column in df.columns else pd.Series([pd.NA] * len(df))
        for value in series:
            total += 1
            if _is_null(value):
                null_count += 1
    return null_count, total


def null_rate(df: pd.DataFrame) -> float:
    """Return the fraction of null/missing values across expected columns."""
    null_count, total = _null_cell_counts(df)
    return null_count / total if total else 0.0


def duplicate_ids(df: pd.DataFrame) -> int:
    """Count rows whose id appears more than once (excluding first occurrence)."""
    if df.empty or "id" not in df.columns:
        return 0

    ids = df["id"]
    seen: set[object] = set()
    duplicates = 0
    for value in ids:
        if _is_null(value):
            continue
        if value in seen:
            duplicates += 1
        else:
            seen.add(value)
    return duplicates


def amount_iqr_outliers(df: pd.DataFrame, *, multiplier: float = IQR_MULTIPLIER) -> int:
    """Count amount values outside Tukey IQR fences."""
    if df.empty or "amount" not in df.columns:
        return 0

    amounts = pd.to_numeric(df["amount"], errors="coerce").dropna()
    amounts = amounts[amounts.map(math.isfinite)]
    if len(amounts) < 2:
        return 0

    q1 = float(amounts.quantile(0.25))
    q3 = float(amounts.quantile(0.75))
    iqr = q3 - q1
    if iqr == 0:
        return 0

    lower = q1 - multiplier * iqr
    upper = q3 + multiplier * iqr
    return int(((amounts < lower) | (amounts > upper)).sum())


def run_checks(
    df: pd.DataFrame | None = None,
    *,
    csv_path: str | Path | None = None,
) -> dict[str, int]:
    """Run quality checks and return check_name -> n_violations."""
    if df is None:
        path = Path(csv_path) if csv_path is not None else DEFAULT_CSV_PATH
        df = load_csv(path)

    null_count, total_cells = _null_cell_counts(df)
    duplicate_count = duplicate_ids(df)
    outlier_count = amount_iqr_outliers(df)
    allowed_nulls = math.floor(MAX_NULL_RATE * total_cells)

    return {
        "null_rate": max(0, null_count - allowed_nulls),
        "duplicate_ids": max(0, duplicate_count - MAX_DUPLICATE_IDS),
        "amount_iqr_outliers": outlier_count,
    }
