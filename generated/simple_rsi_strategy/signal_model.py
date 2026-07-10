"""RSI/MACD features + linear regression signal (research only)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame(
        {
            "macd": macd,
            "macd_signal": macd_signal,
            "macd_hist": macd - macd_signal,
        }
    )


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["rsi"] = compute_rsi(out["close"])
    macd = compute_macd(out["close"])
    out = pd.concat([out, macd], axis=1)
    out["next_return"] = out["close"].pct_change().shift(-1)
    return out.dropna()


def train_model(df: pd.DataFrame) -> dict[str, Any]:
    feat = build_features(df)
    X = feat[["rsi", "macd", "macd_signal", "macd_hist"]].values
    y = (feat["next_return"] > 0).astype(int).values
    model = LinearRegression()
    model.fit(X, y)
    return {"model": model, "feature_cols": ["rsi", "macd", "macd_signal", "macd_hist"]}


def predict_signals(df: pd.DataFrame, trained: dict[str, Any]) -> pd.DataFrame:
    feat = build_features(df)
    model: LinearRegression = trained["model"]
    cols = trained["feature_cols"]
    pred = model.predict(feat[cols].values)
    out = feat.copy()
    out["signal"] = 0
    out.loc[pred > 0.55, "signal"] = 1
    out.loc[pred < 0.45, "signal"] = -1
    return out
