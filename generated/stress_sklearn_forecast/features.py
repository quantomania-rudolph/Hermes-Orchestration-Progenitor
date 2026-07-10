"""Lag return features with shift(1) leakage guard for walk-forward sklearn forecast."""

from __future__ import annotations

import numpy as np
import pandas as pd

try:
    from config import DATE_COLUMN, LABEL_COLUMN, NUM_LAGS, VALUE_COLUMN
except ImportError:  # pragma: no cover - package import when run as module
    from .config import DATE_COLUMN, LABEL_COLUMN, NUM_LAGS, VALUE_COLUMN

FEATURE_COLS: list[str] = [f"return_lag{i}" for i in range(1, NUM_LAGS + 1)]

MIN_ROWS = NUM_LAGS + 2


class LeakageError(ValueError):
    """Raised when a feature frame violates anti-leakage invariants."""


def assert_no_leakage(feature_df: pd.DataFrame) -> None:
    """Fail fast if features leak contemporaneous or future return information."""
    leaked = {LABEL_COLUMN} & set(FEATURE_COLS)
    if leaked:
        raise LeakageError(
            f"FEATURE_COLS must not contain label columns: {sorted(leaked)}"
        )

    if LABEL_COLUMN not in feature_df.columns:
        raise LeakageError(f"feature frame missing label column {LABEL_COLUMN!r}")

    missing = [col for col in FEATURE_COLS if col not in feature_df.columns]
    if missing:
        raise LeakageError(f"feature frame missing columns: {missing}")

    if VALUE_COLUMN not in feature_df.columns:
        return

    value = feature_df[VALUE_COLUMN].astype(float)
    bar_return = value.pct_change()

    label = feature_df[LABEL_COLUMN]
    expected_label = bar_return.shift(-1)
    label_check = pd.concat([label, expected_label], axis=1).dropna()
    if label_check.empty or not label_check.iloc[:, 0].equals(label_check.iloc[:, 1]):
        raise LeakageError(
            f"{LABEL_COLUMN} must be one-bar forward return ({VALUE_COLUMN}.pct_change().shift(-1))"
        )

    for col in FEATURE_COLS:
        if not col.startswith("return_lag"):
            continue
        lag_text = col.removeprefix("return_lag")
        if not lag_text.isdigit():
            continue
        lag_n = int(lag_text)
        series = feature_df[col]
        expected = bar_return if lag_n == 1 else value.pct_change(lag_n)
        expected = expected.shift(1)
        aligned = pd.concat([series, expected], axis=1).dropna()
        if aligned.empty:
            raise LeakageError(f"{col} has no valid rows for shift(1) verification")
        if not aligned.iloc[:, 0].equals(aligned.iloc[:, 1]):
            raise LeakageError(
                f"{col} does not match lag-{lag_n} return shifted by 1 bar"
            )
        contemporaneous = value.pct_change(lag_n)
        leak_check = pd.concat([series, contemporaneous], axis=1).dropna()
        if not leak_check.empty and leak_check.iloc[:, 0].equals(leak_check.iloc[:, 1]):
            raise LeakageError(
                f"{col} equals unshifted {lag_n}-bar return (missing shift(1))"
            )


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build shifted lag-return features and forward ``next_return`` labels."""
    if df is None or df.empty:
        raise ValueError("input DataFrame is empty")

    missing_cols = [col for col in (DATE_COLUMN, VALUE_COLUMN) if col not in df.columns]
    if missing_cols:
        raise ValueError(f"input missing required columns: {missing_cols}")

    if len(df) < MIN_ROWS:
        raise ValueError(
            f"need at least {MIN_ROWS} rows for lag warmup (NUM_LAGS={NUM_LAGS}); "
            f"got {len(df)}"
        )

    work = df.copy()
    work[DATE_COLUMN] = pd.to_datetime(work[DATE_COLUMN])
    work = work.sort_values(DATE_COLUMN).reset_index(drop=True)
    work[VALUE_COLUMN] = pd.to_numeric(work[VALUE_COLUMN], errors="coerce")
    work = work.replace([np.inf, -np.inf], np.nan).dropna(subset=[DATE_COLUMN, VALUE_COLUMN])

    if len(work) < MIN_ROWS:
        raise ValueError(
            f"need at least {MIN_ROWS} valid rows after cleaning; got {len(work)}"
        )

    value = work[VALUE_COLUMN].astype(float)
    bar_return = value.pct_change()

    raw = pd.DataFrame(index=work.index)
    for lag in range(1, NUM_LAGS + 1):
        raw[f"return_lag{lag}"] = value.pct_change(lag)

    shifted = raw[FEATURE_COLS].shift(1)

    out = pd.DataFrame({DATE_COLUMN: work[DATE_COLUMN]})
    out[FEATURE_COLS] = shifted
    out[LABEL_COLUMN] = bar_return.shift(-1)
    out[VALUE_COLUMN] = value

    keep_cols = [DATE_COLUMN, *FEATURE_COLS, LABEL_COLUMN, VALUE_COLUMN]
    out = out[keep_cols].replace([np.inf, -np.inf], np.nan).dropna()

    if out.empty:
        raise ValueError("no rows remain after feature warmup dropna")

    assert_no_leakage(out)
    return out.reset_index(drop=True)
