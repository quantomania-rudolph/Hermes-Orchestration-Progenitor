"""Multi-symbol daily OHLCV loader for the pairs regime UKF research pipeline.

Loader priority:
1. ``market_daily.equity_bars`` via PostgreSQL (asyncpg, 5s timeout)
2. ``sample_data/pairs_universe_bars.csv`` beside this module (offline fallback)

Returns a wide DataFrame indexed by ``ts_utc`` with MultiIndex columns
``(symbol, field)`` where *field* is one of ``open, high, low, close, volume``.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import pandas as pd

from config import LIMIT_BARS, UNIVERSE

logger = logging.getLogger(__name__)

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "data_foundation")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

OUTPUT_FIELDS = ["open", "high", "low", "close", "volume"]
SAMPLE_CSV = Path(__file__).parent / "sample_data" / "pairs_universe_bars.csv"
DB_TIMEOUT_SECONDS = 5
PG_SCHEMA = "market_daily"
PG_TABLE = "equity_bars"


def load_universe_bars(
    symbols: list[str] | None = None,
    *,
    limit_bars: int | None = None,
) -> pd.DataFrame:
    """Load aligned OHLCV bars for the research universe.

    Parameters
    ----------
    symbols:
        Symbol list; defaults to ``config.UNIVERSE``.
    limit_bars:
        Max bars per symbol after alignment; defaults to ``config.LIMIT_BARS``.
    """
    syms = [s.upper() for s in (symbols or UNIVERSE)]
    cap = limit_bars if limit_bars is not None else LIMIT_BARS

    long_df = _load_from_postgres(symbols=syms)
    if long_df is None or not _covers_universe(long_df, syms):
        if long_df is None:
            logger.warning(
                "PostgreSQL unavailable for universe %s; falling back to %s",
                syms,
                SAMPLE_CSV,
            )
        else:
            logger.warning(
                "PostgreSQL incomplete for universe %s; falling back to %s",
                syms,
                SAMPLE_CSV,
            )
        long_df = _load_from_csv(symbols=syms)

    normalized = _normalize_long(long_df)
    missing = [s for s in syms if s not in set(normalized["symbol"])]
    if missing:
        raise ValueError(f"missing bars for symbols after load: {missing}")

    wide = _long_to_wide(normalized, symbols=syms)
    return _apply_limit(wide, cap)


def _covers_universe(df: pd.DataFrame, symbols: list[str]) -> bool:
    if df.empty or "symbol" not in df.columns:
        return False
    present = set(df["symbol"].astype(str).str.upper())
    return all(s in present for s in symbols)


def _load_from_postgres(*, symbols: list[str]) -> pd.DataFrame | None:
    try:
        import asyncpg
    except ImportError:
        logger.info("asyncpg not installed; skipping PostgreSQL load")
        return None

    query = f"""
        SELECT symbol, ts_utc, open, high, low, close, volume
        FROM "{PG_SCHEMA}"."{PG_TABLE}"
        WHERE symbol = ANY($1::text[])
        ORDER BY ts_utc, symbol
    """

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
            rows = await conn.fetch(query, symbols)
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


def _load_from_csv(*, symbols: list[str]) -> pd.DataFrame:
    if not SAMPLE_CSV.is_file():
        raise FileNotFoundError(f"Sample data missing: {SAMPLE_CSV}")
    df = pd.read_csv(SAMPLE_CSV)
    if "symbol" not in df.columns:
        raise ValueError("sample CSV missing column: symbol")
    df["symbol"] = df["symbol"].astype(str).str.upper()
    present = set(df["symbol"].unique())
    missing = [s for s in symbols if s not in present]
    if missing:
        logger.warning("CSV fallback missing symbols %s; returning available subset", missing)
    return df[df["symbol"].isin(symbols)].copy()


def _normalize_long(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        raise ValueError("no bars returned for universe load")

    out = df.copy()
    for col in ("symbol", "ts_utc"):
        if col not in out.columns:
            raise ValueError(f"bar frame missing column: {col}")

    out["symbol"] = out["symbol"].astype(str).str.upper()
    out["ts_utc"] = pd.to_datetime(out["ts_utc"], utc=True)
    for col in OUTPUT_FIELDS:
        if col not in out.columns:
            raise ValueError(f"bar frame missing column: {col}")
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out = out.dropna(subset=["symbol", "ts_utc", *OUTPUT_FIELDS])
    out = out.drop_duplicates(subset=["symbol", "ts_utc"], keep="last")
    out = out.sort_values(["ts_utc", "symbol"]).reset_index(drop=True)
    return out


def _long_to_wide(df: pd.DataFrame, *, symbols: list[str]) -> pd.DataFrame:
    pieces: list[pd.DataFrame] = []
    for sym in symbols:
        sub = df.loc[df["symbol"] == sym].set_index("ts_utc")[OUTPUT_FIELDS]
        if sub.empty:
            continue
        sub.columns = pd.MultiIndex.from_product([[sym], sub.columns])
        pieces.append(sub)

    if not pieces:
        raise ValueError(f"no bars available for requested symbols: {symbols}")

    wide = pd.concat(pieces, axis=1).sort_index()
    wide = wide.sort_index(axis=1)
    wide = wide[~wide.index.duplicated(keep="last")]
    wide = wide.dropna(how="any")
    if wide.empty:
        raise ValueError(f"no aligned bars across universe: {symbols}")
    wide.index.name = "ts_utc"
    return wide


def _apply_limit(wide: pd.DataFrame, limit_bars: int) -> pd.DataFrame:
    if limit_bars <= 0 or len(wide) <= limit_bars:
        return wide
    return wide.iloc[-limit_bars:].copy()
