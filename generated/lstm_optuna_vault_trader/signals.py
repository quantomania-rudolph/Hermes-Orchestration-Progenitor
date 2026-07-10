"""Leakage-safe technical signals for the LSTM + Optuna vault-equity pipeline.

All features are shifted one bar: value at ``t`` uses OHLCV observed at or before
``bar_end_utc[t-1]``. Labels (``next_return``, ``next_direction``) are forward-shifted
returns and are never included in ``FEATURE_COLS``.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from config import LOOKBACK

RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL_SPAN = 9
BB_PERIOD = 20
BB_STD_MULT = 2.0
ATR_PERIOD = 14
ROLLING_VOL_PERIOD = 20
MACD_WARMUP = 26
ROLLING_WARMUP = 20
MIN_EXTRA_BARS = 10
RTH_MINUTES = 390

MIN_ROWS = LOOKBACK + MACD_WARMUP + ROLLING_WARMUP + MIN_EXTRA_BARS

LABEL_COL = "next_return"
DIRECTION_COL = "next_direction"

FEATURE_COLS: list[str] = [
    "return_lag1",
    "return_lag5",
    "rolling_vol",
    "rsi",
    "macd",
    "macd_signal",
    "macd_hist",
    "bb_pct_b",
    "atr_norm",
    "session_progress",
]

_ET = ZoneInfo("America/New_York")
_REQUIRED_OHLCV = ("open", "high", "low", "close", "volume")


class LeakageError(ValueError):
    """Raised when a feature frame violates anti-leakage invariants."""


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _wilder_rsi(close: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))

    neutral = (avg_loss == 0.0) & (avg_gain == 0.0)
    max_rsi = (avg_loss == 0.0) & (avg_gain > 0.0)
    rsi = rsi.where(~neutral, 50.0)
    rsi = rsi.where(~max_rsi, 100.0)
    return rsi.fillna(50.0)


def _macd_trio(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    macd_line = _ema(close, MACD_FAST) - _ema(close, MACD_SLOW)
    macd_signal = _ema(macd_line, MACD_SIGNAL_SPAN)
    macd_hist = macd_line - macd_signal
    return macd_line, macd_signal, macd_hist


def _bb_pct_b(close: pd.Series) -> pd.Series:
    mid = close.rolling(BB_PERIOD, min_periods=BB_PERIOD).mean()
    std = close.rolling(BB_PERIOD, min_periods=BB_PERIOD).std()
    upper = mid + BB_STD_MULT * std
    lower = mid - BB_STD_MULT * std
    width = upper - lower
    pct_b = (close - lower) / width
    pct_b = np.where(width > 1e-12, pct_b, 0.5)
    return pd.Series(np.clip(pct_b, 0.0, 1.0), index=close.index, dtype=float)


def _wilder_atr(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / ATR_PERIOD, min_periods=ATR_PERIOD, adjust=False).mean()


def _session_progress(bar_end_utc: pd.Series) -> pd.Series:
    ts = pd.to_datetime(bar_end_utc, utc=True)
    ts_et = ts.dt.tz_convert(_ET)
    rth_open = ts_et.dt.normalize() + pd.Timedelta(hours=9, minutes=30)
    minutes = (ts_et - rth_open).dt.total_seconds() / 60.0
    progress = minutes / RTH_MINUTES
    in_rth = (minutes >= 0.0) & (minutes <= RTH_MINUTES)
    out = np.where(in_rth, np.clip(progress, 0.0, 1.0), 0.0)
    return pd.Series(out, index=bar_end_utc.index, dtype=float)


def _compute_raw_features(df: pd.DataFrame) -> pd.DataFrame:
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)

    bar_return = close.pct_change()
    atr = _wilder_atr(high, low, close)
    macd_line, macd_signal, macd_hist = _macd_trio(close)

    features = pd.DataFrame(index=df.index)
    features["return_lag1"] = bar_return
    features["return_lag5"] = close.pct_change(5)
    features["rolling_vol"] = bar_return.rolling(
        ROLLING_VOL_PERIOD, min_periods=ROLLING_VOL_PERIOD
    ).std()
    features["rsi"] = _wilder_rsi(close, RSI_PERIOD)
    features["macd"] = macd_line
    features["macd_signal"] = macd_signal
    features["macd_hist"] = macd_hist
    features["bb_pct_b"] = _bb_pct_b(close)
    features["atr_norm"] = atr / close.replace(0.0, np.nan)
    features["session_progress"] = _session_progress(df["bar_end_utc"])
    return features


def assert_no_leakage(feature_df: pd.DataFrame) -> None:
    """Fail fast if features leak contemporaneous or future return information."""
    leaked = {"next_return", "next_direction"} & set(FEATURE_COLS)
    if leaked:
        raise LeakageError(f"FEATURE_COLS must not contain label columns: {sorted(leaked)}")

    if LABEL_COL not in feature_df.columns:
        raise LeakageError(f"feature frame missing label column {LABEL_COL!r}")

    missing = [col for col in FEATURE_COLS if col not in feature_df.columns]
    if missing:
        raise LeakageError(f"feature frame missing columns: {missing}")

    if "close" in feature_df.columns:
        unshifted_return = feature_df["close"].astype(float).pct_change()
    else:
        unshifted_return = None

    label = feature_df[LABEL_COL]
    for col in FEATURE_COLS:
        series = feature_df[col]
        if unshifted_return is not None:
            aligned = pd.concat([series, unshifted_return], axis=1).dropna()
            if not aligned.empty and aligned.iloc[:, 0].equals(aligned.iloc[:, 1]):
                raise LeakageError(f"{col} equals unshifted contemporaneous return")

        valid = pd.concat([series, label], axis=1).dropna()
        if not valid.empty and valid.iloc[:, 0].equals(valid.iloc[:, 1]):
            raise LeakageError(f"{col} equals {LABEL_COL}")
        if len(valid) < 3:
            continue
        corr = valid.iloc[:, 0].corr(valid.iloc[:, 1])
        if corr is not None and abs(corr) > 0.999:
            raise LeakageError(
                f"{col} correlates with {LABEL_COL} at {corr:.6f} (> 0.999 threshold)"
            )


def build_feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Build shifted features and forward labels from loader OHLCV bars."""
    if df is None or df.empty:
        raise ValueError("input DataFrame is empty")

    missing_cols = [col for col in ("bar_end_utc", *_REQUIRED_OHLCV) if col not in df.columns]
    if missing_cols:
        raise ValueError(f"input missing required columns: {missing_cols}")

    if len(df) < MIN_ROWS:
        raise ValueError(
            f"need at least {MIN_ROWS} bars for warmup "
            f"(LOOKBACK={LOOKBACK}, MACD={MACD_WARMUP}, rolling={ROLLING_WARMUP}, "
            f"buffer={MIN_EXTRA_BARS}); got {len(df)}"
        )

    work = df.copy()
    work["bar_end_utc"] = pd.to_datetime(work["bar_end_utc"], utc=True)
    work = work.sort_values("bar_end_utc").reset_index(drop=True)

    for col in _REQUIRED_OHLCV:
        work[col] = pd.to_numeric(work[col], errors="coerce")
    work = work.replace([np.inf, -np.inf], np.nan)
    work = work.dropna(subset=["bar_end_utc", *_REQUIRED_OHLCV])

    if len(work) < MIN_ROWS:
        raise ValueError(
            f"need at least {MIN_ROWS} valid bars after cleaning; got {len(work)}"
        )

    raw_features = _compute_raw_features(work)
    shifted = raw_features[FEATURE_COLS].shift(1)

    bar_return = work["close"].pct_change()
    out = pd.DataFrame({"bar_end_utc": work["bar_end_utc"]})
    out[FEATURE_COLS] = shifted
    out[LABEL_COL] = bar_return.shift(-1)
    out["close"] = work["close"].astype(float)

    keep_cols = ["bar_end_utc", *FEATURE_COLS, LABEL_COL, "close"]
    out = out[keep_cols].replace([np.inf, -np.inf], np.nan).dropna()
    out[DIRECTION_COL] = np.sign(out[LABEL_COL]).astype(int)

    if out.empty:
        raise ValueError("no rows remain after feature warmup dropna")

    assert_no_leakage(out)
    return out.reset_index(drop=True)
