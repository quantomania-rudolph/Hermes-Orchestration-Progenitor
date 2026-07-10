"""CSV ingest with pydantic row validation."""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

try:
    from schema import TransactionRow
except ImportError:  # pragma: no cover - package import when run as module
    from .schema import TransactionRow

__all__ = ["load_csv", "collect_validation_errors"]

_EXPECTED_COLUMNS = ("id", "amount", "category", "timestamp")


def _normalize_cell(value: object) -> object:
    """Map pandas missing sentinels to None for pydantic validation."""
    if value is None or value is pd.NA:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def load_csv(path: str | Path) -> pd.DataFrame:
    """Load a transactions CSV into a DataFrame without dropping rows."""
    csv_path = Path(path)
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    try:
        df = pd.read_csv(csv_path, keep_default_na=True, on_bad_lines="error")
    except TypeError:
        # pandas < 1.3
        df = pd.read_csv(csv_path, keep_default_na=True, error_bad_lines=True)

    for column in _EXPECTED_COLUMNS:
        if column not in df.columns:
            df[column] = pd.NA
    return df.reset_index(drop=True)


def collect_validation_errors(df: pd.DataFrame) -> list[ValidationError]:
    """Validate each row against TransactionRow; return one error per invalid row."""
    errors: list[ValidationError] = []
    for i in range(len(df)):
        row = df.iloc[i]
        record = {
            col: _normalize_cell(row[col] if col in row.index else pd.NA)
            for col in _EXPECTED_COLUMNS
        }
        try:
            TransactionRow.model_validate(record)
        except ValidationError as exc:
            errors.append(exc)
    return errors
