"""Historical OHLCV retrieval via yfinance with a local on-disk cache.

Returns a pandas DataFrame indexed by tz-aware datetime with lowercase
columns: open, high, low, close, volume. 4h is synthesised by resampling 1h
because yfinance has no native 4h interval.
"""
from __future__ import annotations

import os
import time

import pandas as pd

try:
    import yfinance as yf
    # yfinance logs noisy "possibly delisted; no price data" messages for
    # symbols/intervals that legitimately return nothing (e.g. futures 1m on a
    # quiet period). We handle empties ourselves, so silence its logger.
    import logging
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
except Exception:  # pragma: no cover - import guard for first run
    yf = None

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(APP_ROOT, ".cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# timeframe -> (yfinance interval, default period, cache TTL seconds)
TIMEFRAMES = {
    "1m": ("1m", "7d", 60),
    "5m": ("5m", "60d", 120),
    "15m": ("15m", "60d", 300),
    "30m": ("30m", "60d", 300),
    "1h": ("60m", "730d", 600),
    "4h": ("60m", "730d", 600),   # resampled from 60m
    "1d": ("1d", "max", 1800),
    "1w": ("1wk", "max", 3600),
}

ALL_TIMEFRAMES = list(TIMEFRAMES.keys())

# pandas resample rule for synthetic timeframes
_RESAMPLE = {"4h": "4h"}


def _cache_path(ticker: str, timeframe: str) -> str:
    safe = ticker.replace("=", "_").replace("/", "_").replace("^", "_")
    return os.path.join(CACHE_DIR, f"{safe}__{timeframe}.pkl")


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    # yfinance may return a MultiIndex column frame for single tickers
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)
    keep = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    df = df[keep].copy()
    df = df[~df.index.duplicated(keep="last")]
    df = df.dropna(how="all")
    # forward-fill price gaps but keep volume zeros for missing candles
    df[["open", "high", "low", "close"]] = df[["open", "high", "low", "close"]].ffill()
    df["volume"] = df["volume"].fillna(0)
    df = df.dropna(subset=["close"])
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    return df


def _resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    if df.empty:
        return df
    agg = {"open": "first", "high": "max", "low": "min",
           "close": "last", "volume": "sum"}
    out = df.resample(rule, label="left", closed="left").agg(agg)
    return out.dropna(subset=["open"])


def fetch(ticker: str, timeframe: str, use_cache: bool = True) -> pd.DataFrame:
    """Fetch OHLCV for ticker/timeframe. Reads cache when fresh."""
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    interval, period, ttl = TIMEFRAMES[timeframe]
    path = _cache_path(ticker, timeframe)

    if use_cache and os.path.exists(path):
        if time.time() - os.path.getmtime(path) < ttl:
            try:
                return pd.read_pickle(path)
            except Exception:
                pass

    if yf is None:
        # cache-only mode if yfinance unavailable
        if os.path.exists(path):
            return pd.read_pickle(path)
        return _normalize(None)

    try:
        raw = yf.download(
            ticker, interval=interval, period=period,
            auto_adjust=False, progress=False, threads=False,
        )
    except Exception as exc:  # network / symbol errors
        print(f"[fetcher] download failed for {ticker} {timeframe}: {exc}")
        if os.path.exists(path):
            return pd.read_pickle(path)
        return _normalize(None)

    df = _normalize(raw)
    if timeframe in _RESAMPLE:
        df = _resample(df, _RESAMPLE[timeframe])

    if not df.empty:
        try:
            df.to_pickle(path)
        except Exception:
            pass
    return df


def latest_price(ticker: str) -> float | None:
    """Quick last-price lookup used by the polling fallback.

    Uses Ticker.fast_info first (works for stocks, ETFs, futures and forex even
    when intraday history is momentarily empty), then falls back to recent bars.
    """
    if yf is None:
        return None
    # 1) fast_info quote — most reliable across asset classes
    try:
        fi = yf.Ticker(ticker).fast_info
        price = getattr(fi, "last_price", None)
        if price is not None and price == price and price > 0:  # not NaN
            return float(price)
    except Exception:
        pass
    # 2) fall back to the most recent bar from a few period/interval combos
    for period, interval in (("1d", "1m"), ("5d", "5m"), ("5d", "1d")):
        try:
            df = _normalize(yf.download(ticker, period=period, interval=interval,
                                        progress=False, threads=False))
            if not df.empty:
                return float(df["close"].iloc[-1])
        except Exception:
            continue
    return None
