"""Vault-equity OHLCV bar loader for the LSTM + Optuna research pipeline.

FILE OF DATA cleaning lineage (do not re-apply upstream filters in Python)
---------------------------------------------------------------------------

Source-of-truth paths
~~~~~~~~~~~~~~~~~~~~~
- ``C:\\Users\\Rudol\\Desktop\\FILE OF DATA\\Vault\\vault_equity (1).ipynb``
  FMP stable ingest → ``market_{5,15}min.equity_bars``
- ``FILE OF DATA\\DONE\\sql\\`` — sessions, atoms materialized views, PIT universe,
  walkforward splits
- ``FILE OF DATA\\DONE\\Bar end leakage\\`` — ``*_bars_bt`` views with
  ``bar_end_utc = ts_utc + interval``
- ``FILE OF DATA\\Calendar and Sessions\\`` — NYSE calendar, RTH window audits
- ``FILE OF DATA\\splits and corporate actions\\`` — FMP splits/events staging;
  PIT leakage audits
- ``FILE OF DATA\\PIPELINE_GAMEPLAN.txt`` — full refresh phase order A→H

Vault ingest (notebook contract)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- FMP stable base: ``https://financialmodelingprep.com/stable`` (env ``FMP_BASE``)
- Endpoints: ``historical-chart/{5min,15min}`` bars only
  (``WRITE_INDICATORS = False``)
- Session filter at ingest: RTH 09:30–16:00 ET, Mon–Fri (``SESSION_FILTER = True``)
- Leakage guard: drop partially formed trailing bars (``LEAKAGE_GUARD_MINUTES``)
- DB: ``data_foundation``, schemas ``market_5min``, ``market_15min``
- Unique key: ``(symbol, ts_utc)`` on ``equity_bars``

Post-ingest SQL / atoms (Phase B–G)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
1. ``alpha_atoms.refresh_materialized_atoms()`` builds
   ``atoms_5min_mkt`` / ``atoms_15min_mkt`` via session-window join to
   ``alpha_meta.us_equity_sessions``.
2. Atom rows use ``bar_end_utc`` as the observation anchor for features and labels.
3. Walkforward splits join on ``bar_end_utc`` (never raw ``ts_utc`` for intraday).
4. ``market_5min.equity_bars_bt`` adds ``bar_end_utc = ts_utc + interval`` with
   leakage audits targeting zero violations.
5. Calendar, splits, and leakage verification suites gate mining readiness.

Loader priority (this module)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
1. ``alpha_atoms.atoms_5min_mkt`` / ``atoms_15min_mkt`` (preferred)
2. ``market_{interval}.equity_bars_bt``
3. ``sample_data/aapl_5min_sample.csv`` (offline / CI fallback)

PostgreSQL access is optional (``asyncpg``); connection attempts time out after 5s.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Literal

import pandas as pd

from config import LIMIT_BARS

logger = logging.getLogger(__name__)

FMP_BASE = os.getenv("FMP_BASE", "https://financialmodelingprep.com/stable").rstrip("/")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "data_foundation")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

BARS_INTERVALS = ("5min", "15min")
INTERVAL_MINUTES = {"5min": 5, "15min": 15}
OUTPUT_COLUMNS = ["bar_end_utc", "open", "high", "low", "close", "volume"]
SAMPLE_CSV = Path(__file__).parent / "sample_data" / "aapl_5min_sample.csv"
DB_TIMEOUT_SECONDS = 5

SourceKind = Literal["atoms", "bars_bt", "bars_raw", "auto"]


def load_bars(
    symbol: str = "AAPL",
    interval: str = "5min",
    *,
    source: SourceKind = "auto",
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int | None = None,
) -> pd.DataFrame:
    """Load OHLCV bars keyed by ``bar_end_utc``.

    Returns a DataFrame with columns ``bar_end_utc, open, high, low, close, volume``
    sorted ascending by ``bar_end_utc`` (tz-aware UTC).
    """
    _validate_interval(interval)
    row_limit = LIMIT_BARS if limit is None else limit

    loaders: list[tuple[str, str]]
    if source == "auto":
        loaders = [
            ("atoms", _load_from_atoms),
            ("bars_bt", _load_from_bars_bt),
            ("csv", _load_from_csv),
        ]
    elif source == "atoms":
        loaders = [("atoms", _load_from_atoms), ("csv", _load_from_csv)]
    elif source == "bars_bt":
        loaders = [("bars_bt", _load_from_bars_bt), ("csv", _load_from_csv)]
    elif source == "bars_raw":
        loaders = [("bars_raw", _load_from_bars_raw), ("csv", _load_from_csv)]
    else:
        raise ValueError(f"unsupported source {source!r}")

    last_error: Exception | None = None
    for source_name, loader in loaders:
        try:
            raw = loader(symbol=symbol, interval=interval, limit=row_limit)
            if raw is None or raw.empty:
                logger.info("loader %s returned no rows for %s %s", source_name, symbol, interval)
                continue
            df = _normalize_bars(raw, interval=interval, symbol=symbol)
            df = _apply_time_filters(df, start=start, end=end)
            if row_limit is not None:
                df = df.head(row_limit)
            if df.empty:
                continue
            _log_load_summary(df, source_name, symbol, interval)
            return df
        except FileNotFoundError:
            raise
        except Exception as exc:
            last_error = exc
            logger.warning("loader %s failed for %s %s: %s", source_name, symbol, interval, exc)

    if last_error is not None:
        raise RuntimeError(
            f"unable to load bars for {symbol} {interval}; last error: {last_error}"
        )
    raise RuntimeError(f"no bars loaded for {symbol} {interval}")


def _validate_interval(interval: str) -> None:
    if interval not in BARS_INTERVALS:
        raise ValueError(f"unsupported interval {interval!r}; expected one of {BARS_INTERVALS}")


def _schema_for_interval(interval: str) -> str:
    return f"market_{interval}"


def _atoms_table_for_interval(interval: str) -> str:
    return f"alpha_atoms.atoms_{interval}_mkt"


def _load_from_db(
    query: str,
    params: list[object],
) -> pd.DataFrame | None:
    try:
        import asyncpg
    except ImportError:
        logger.info("asyncpg not installed; skipping PostgreSQL load")
        return None

    import asyncio

    async def _fetch() -> pd.DataFrame:
        conn = await asyncpg.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            timeout=DB_TIMEOUT_SECONDS,
            command_timeout=DB_TIMEOUT_SECONDS,
        )
        try:
            rows = await conn.fetch(query, *params)
        finally:
            await conn.close()
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame([dict(r) for r in rows])

    try:
        return asyncio.run(asyncio.wait_for(_fetch(), timeout=DB_TIMEOUT_SECONDS))
    except TimeoutError:
        logger.warning("PostgreSQL fetch timed out after %ss", DB_TIMEOUT_SECONDS)
        return None
    except Exception as exc:
        logger.warning("PostgreSQL fetch failed: %s", exc)
        return None


def _load_from_atoms(*, symbol: str, interval: str, limit: int) -> pd.DataFrame | None:
    table = _atoms_table_for_interval(interval)
    query = f"""
        SELECT bar_end_utc, open, high, low, close, volume
        FROM {table}
        WHERE instrument = $1
          AND interval_label = $2
        ORDER BY bar_end_utc
        LIMIT $3
    """
    return _load_from_db(query, [symbol, interval, limit])


def _load_from_bars_bt(*, symbol: str, interval: str, limit: int) -> pd.DataFrame | None:
    schema = _schema_for_interval(interval)
    query = f"""
        SELECT bar_end_utc, open, high, low, close, volume
        FROM "{schema}"."equity_bars_bt"
        WHERE symbol = $1
        ORDER BY bar_end_utc
        LIMIT $2
    """
    df = _load_from_db(query, [symbol, limit])
    if df is not None and not df.empty:
        return df

    # Some deployments expose ts_utc only on the bt view.
    query_ts = f"""
        SELECT ts_utc, open, high, low, close, volume
        FROM "{schema}"."equity_bars_bt"
        WHERE symbol = $1
        ORDER BY ts_utc
        LIMIT $2
    """
    return _load_from_db(query_ts, [symbol, limit])


def _load_from_bars_raw(*, symbol: str, interval: str, limit: int) -> pd.DataFrame | None:
    logger.warning("loading legacy equity_bars without bar_end view; prefer atoms or bars_bt")
    schema = _schema_for_interval(interval)
    query = f"""
        SELECT ts_utc, open, high, low, close, volume
        FROM "{schema}"."equity_bars"
        WHERE symbol = $1
        ORDER BY ts_utc
        LIMIT $2
    """
    return _load_from_db(query, [symbol, limit])


def _load_from_csv(*, symbol: str, interval: str, limit: int) -> pd.DataFrame:
    del symbol, interval
    if not SAMPLE_CSV.is_file():
        raise FileNotFoundError(f"Sample data missing: {SAMPLE_CSV}")
    df = pd.read_csv(SAMPLE_CSV)
    if "ts_utc" in df.columns:
        df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True)
    if limit is not None:
        df = df.head(limit)
    return df


def _normalize_bars(df: pd.DataFrame, *, interval: str, symbol: str) -> pd.DataFrame:
    out = df.copy()
    minutes = INTERVAL_MINUTES[interval]

    if "bar_end_utc" not in out.columns:
        if "bar_start_utc" in out.columns:
            out["bar_end_utc"] = pd.to_datetime(out["bar_start_utc"], utc=True) + pd.Timedelta(
                minutes=minutes
            )
        elif "ts_utc" in out.columns:
            out["bar_end_utc"] = pd.to_datetime(out["ts_utc"], utc=True) + pd.Timedelta(
                minutes=minutes
            )
        else:
            raise ValueError("bar frame missing bar_end_utc, bar_start_utc, or ts_utc")

    out["bar_end_utc"] = pd.to_datetime(out["bar_end_utc"], utc=True)
    for col in ("open", "high", "low", "close"):
        if col not in out.columns:
            raise ValueError(f"bar frame missing column: {col}")
        out[col] = pd.to_numeric(out[col], errors="coerce")
    if "volume" not in out.columns:
        raise ValueError("bar frame missing column: volume")
    out["volume"] = pd.to_numeric(out["volume"], errors="coerce")

    dup_cols = ["bar_end_utc"]
    if "instrument" in out.columns:
        dup_cols = ["instrument", "bar_end_utc"]

    out = out.dropna(subset=["bar_end_utc", "open", "high", "low", "close", "volume"])
    out = out.drop_duplicates(subset=dup_cols, keep="last")
    out = out.sort_values("bar_end_utc").reset_index(drop=True)
    out = out[OUTPUT_COLUMNS].copy()
    out.attrs["symbol"] = symbol
    return out


def _apply_time_filters(
    df: pd.DataFrame,
    *,
    start: datetime | None,
    end: datetime | None,
) -> pd.DataFrame:
    if df.empty:
        return df
    out = df
    if start is not None:
        start_ts = pd.Timestamp(start)
        if start_ts.tzinfo is None:
            start_ts = start_ts.tz_localize("UTC")
        else:
            start_ts = start_ts.tz_convert("UTC")
        out = out[out["bar_end_utc"] >= start_ts]
    if end is not None:
        end_ts = pd.Timestamp(end)
        if end_ts.tzinfo is None:
            end_ts = end_ts.tz_localize("UTC")
        else:
            end_ts = end_ts.tz_convert("UTC")
        out = out[out["bar_end_utc"] <= end_ts]
    return out.reset_index(drop=True)


def _log_load_summary(df: pd.DataFrame, source: str, symbol: str, interval: str) -> None:
    logger.info(
        "load_bars source=%s symbol=%s interval=%s rows=%d bar_end_utc=[%s .. %s]",
        source,
        symbol,
        interval,
        len(df),
        df["bar_end_utc"].iloc[0],
        df["bar_end_utc"].iloc[-1],
    )
