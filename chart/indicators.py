"""Pure indicator calculations operating on an OHLCV DataFrame.

Every function returns numpy arrays / pandas Series aligned to the input index
so the chart engine can plot them directly against candle x-positions.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(df: pd.DataFrame, period: int) -> pd.Series:
    return df["close"].rolling(period, min_periods=1).mean()


def ema(df: pd.DataFrame, period: int) -> pd.Series:
    return df["close"].ewm(span=period, adjust=False).mean()


def rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    delta = df["close"].diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50.0)


def macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9):
    fast_ema = df["close"].ewm(span=fast, adjust=False).mean()
    slow_ema = df["close"].ewm(span=slow, adjust=False).mean()
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def bollinger(df: pd.DataFrame, period: int = 20, mult: float = 2.0):
    mid = df["close"].rolling(period, min_periods=1).mean()
    std = df["close"].rolling(period, min_periods=1).std(ddof=0)
    upper = mid + mult * std
    lower = mid - mult * std
    return upper, mid, lower


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=1).mean()


def _session_key(index: pd.DatetimeIndex) -> np.ndarray:
    """Group rows by trading day (UTC date) for session resets."""
    return index.tz_convert("UTC").normalize().values


def vwap(df: pd.DataFrame, with_bands: bool = True):
    """Session-resetting VWAP with optional 1/2 SD bands.

    Returns dict with keys: vwap, upper1, lower1, upper2, lower2.
    """
    if df.empty:
        empty = pd.Series(dtype=float)
        return {k: empty for k in ("vwap", "upper1", "lower1", "upper2", "lower2")}
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    vol = df["volume"].replace(0, np.nan).ffill().fillna(1.0)
    sess = _session_key(df.index)
    tpv = tp * vol
    g = pd.DataFrame({"sess": sess, "tpv": tpv.values, "vol": vol.values,
                      "tp": tp.values}, index=df.index)
    cum_tpv = g.groupby("sess")["tpv"].cumsum()
    cum_vol = g.groupby("sess")["vol"].cumsum()
    vw = cum_tpv / cum_vol
    out = {"vwap": vw}
    if with_bands:
        # variance of typical price weighted by volume, per session
        cum_tp2v = g.assign(tp2v=g["tp"] ** 2 * g["vol"]).groupby("sess")["tp2v"].cumsum()
        var = (cum_tp2v / cum_vol) - vw ** 2
        std = np.sqrt(var.clip(lower=0))
        out.update({
            "upper1": vw + std, "lower1": vw - std,
            "upper2": vw + 2 * std, "lower2": vw - 2 * std,
        })
    return out


def volume_ma(df: pd.DataFrame, period: int = 20) -> pd.Series:
    return df["volume"].rolling(period, min_periods=1).mean()
