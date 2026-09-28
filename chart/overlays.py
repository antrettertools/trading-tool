"""AMT (Auction Market Theory) overlay calculations.

Computes prior-period value areas (day / week / month), session open lines,
overnight range, and naked POC detection. Results are plain dicts / lists that
the chart engine renders as horizontal lines and labels.
"""
from __future__ import annotations

import pandas as pd

from chart.profiles import volume_profile


def _period_groups(df: pd.DataFrame, freq: str):
    """Yield (label, sub_df) per calendar period using a resample grouper."""
    if df.empty:
        return
    grouper = df.groupby(pd.Grouper(freq=freq))
    for label, sub in grouper:
        if not sub.empty:
            yield label, sub


def prior_period_levels(df: pd.DataFrame, freq: str, bins: int = 40,
                        va_pct: float = 0.70) -> dict | None:
    """VAH/VAL/POC for the most recently *completed* period of ``freq``.

    freq: 'D' (day), 'W' (week), 'ME' (month).
    """
    groups = list(_period_groups(df, freq))
    if len(groups) < 2:
        return None
    # second-to-last completed period (last may still be developing)
    _, sub = groups[-2]
    prof = volume_profile(sub, bins=bins, va_pct=va_pct)
    if prof is None:
        return None
    return {"vah": prof.vah, "val": prof.val, "poc": prof.poc_price}


def session_open(df: pd.DataFrame) -> float | None:
    """Open price of the most recent session (UTC day)."""
    groups = list(_period_groups(df, "D"))
    if not groups:
        return None
    _, sub = groups[-1]
    return float(sub["open"].iloc[0])


def overnight_range(df: pd.DataFrame, rth_start_hour_utc: int = 13,
                    rth_end_hour_utc: int = 20) -> dict | None:
    """High/low formed outside the regular trading hours of the latest day.

    Defaults approximate US RTH (09:30-16:00 ET) expressed in UTC.
    """
    groups = list(_period_groups(df, "D"))
    if not groups:
        return None
    _, sub = groups[-1]
    hours = sub.index.tz_convert("UTC").hour
    on = sub[(hours < rth_start_hour_utc) | (hours >= rth_end_hour_utc)]
    if on.empty:
        return None
    return {"high": float(on["high"].max()), "low": float(on["low"].min())}


def session_boundaries(df: pd.DataFrame) -> list:
    """x-index positions (row offsets) where a new session/day begins."""
    if df.empty:
        return []
    days = df.index.tz_convert("UTC").normalize()
    boundaries = []
    prev = None
    for i, d in enumerate(days):
        if prev is not None and d != prev:
            boundaries.append(i)
        prev = d
    return boundaries


def weekend_gaps(df: pd.DataFrame) -> list[tuple[int, int]]:
    """Pairs of (index_before_gap, index_after_gap) spanning a weekend break."""
    if df.empty:
        return []
    gaps = []
    idx = df.index
    for i in range(1, len(idx)):
        delta = (idx[i] - idx[i - 1])
        if delta > pd.Timedelta(days=2):
            gaps.append((i - 1, i))
    return gaps


def naked_pocs(df: pd.DataFrame, freq: str = "D", bins: int = 40,
               lookback: int = 20) -> list[float]:
    """POC levels from prior sessions that price has not traded back through.

    For each completed session we take its volume POC, then check whether any
    later candle's high-low range covered that level. Untouched ('naked') POCs
    are returned.
    """
    groups = list(_period_groups(df, freq))
    if len(groups) < 2:
        return []
    groups = groups[-(lookback + 1):]
    naked = []
    for gi in range(len(groups) - 1):
        _, sub = groups[gi]
        prof = volume_profile(sub, bins=bins)
        if prof is None:
            continue
        poc = prof.poc_price
        # candles after this session
        after_start = sub.index[-1]
        later = df[df.index > after_start]
        touched = ((later["low"] <= poc) & (later["high"] >= poc)).any()
        if not touched:
            naked.append(poc)
    return naked
