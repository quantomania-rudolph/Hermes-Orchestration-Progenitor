"""Load equity bars — vault_equity contract with CSV fallback."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

# Mirrors vault_equity (1).ipynb stable API / DB settings
FMP_BASE = os.getenv("FMP_BASE", "https://financialmodelingprep.com/stable").rstrip("/")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "data_foundation")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

SAMPLE_CSV = Path(__file__).parent / "sample_data" / "aapl_5min_sample.csv"


def load_bars(symbol: str = "AAPL", interval: str = "5min") -> pd.DataFrame:
    """Load OHLCV bars from PostgreSQL equity_bars or fall back to sample CSV."""
    df = _load_from_db(symbol, interval)
    if df is not None and not df.empty:
        return df
    return _load_from_csv(symbol)


def _load_from_db(symbol: str, interval: str) -> pd.DataFrame | None:
    try:
        import asyncpg  # noqa: F401
    except ImportError:
        return None
    try:
        import asyncio

        async def _fetch() -> pd.DataFrame:
            conn = await asyncpg.connect(
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                timeout=5,
            )
            rows = await conn.fetch(
                """
                SELECT ts_utc, open, high, low, close, volume, symbol
                FROM equity_bars
                WHERE symbol = $1 AND interval = $2
                ORDER BY ts_utc
                LIMIT 5000
                """,
                symbol,
                interval,
            )
            await conn.close()
            if not rows:
                return pd.DataFrame()
            return pd.DataFrame([dict(r) for r in rows])

        return asyncio.run(_fetch())
    except Exception:
        return None


def _load_from_csv(symbol: str) -> pd.DataFrame:
    if not SAMPLE_CSV.is_file():
        raise FileNotFoundError(f"Sample data missing: {SAMPLE_CSV}")
    df = pd.read_csv(SAMPLE_CSV, parse_dates=["ts_utc"])
    df["symbol"] = symbol
    required = ["ts_utc", "open", "high", "low", "close", "volume", "symbol"]
    return df[required].sort_values("ts_utc").reset_index(drop=True)
