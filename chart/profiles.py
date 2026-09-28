"""Volume Profile and Market Profile (TPO) calculations.

These are pure-data computations returning dataclasses; the chart engine turns
them into pyqtgraph items. Both compute POC / Value Area; Volume Profile uses
traded volume per price bin, Market Profile counts 30-minute TPO periods.
"""
from __future__ import annotations

import string
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

TPO_LETTERS = string.ascii_uppercase + string.ascii_lowercase


@dataclass
class ProfileResult:
    bin_centers: np.ndarray            # price level of each bin
    counts: np.ndarray                 # volume or TPO count per bin
    bin_size: float
    poc_price: float
    vah: float
    val: float
    total: float


def _value_area(centers: np.ndarray, counts: np.ndarray, va_pct: float):
    """Expand around POC until va_pct of total is captured (standard method)."""
    if counts.sum() <= 0:
        return float(centers[0]), float(centers[0]), float(centers[-1])
    poc_idx = int(np.argmax(counts))
    target = counts.sum() * va_pct
    included = counts[poc_idx]
    lo = hi = poc_idx
    n = len(counts)
    while included < target and (lo > 0 or hi < n - 1):
        below = counts[lo - 1] if lo > 0 else -1
        above = counts[hi + 1] if hi < n - 1 else -1
        if above >= below:
            hi += 1
            included += counts[hi]
        else:
            lo -= 1
            included += counts[lo]
    return float(centers[poc_idx]), float(centers[hi]), float(centers[lo])


def volume_profile(df: pd.DataFrame, bins: int = 40,
                   va_pct: float = 0.70) -> ProfileResult | None:
    """Volume distributed across price bins. Each candle's volume is spread
    uniformly over the bins its high-low range touches."""
    if df is None or df.empty:
        return None
    lo = float(df["low"].min())
    hi = float(df["high"].max())
    if hi <= lo:
        hi = lo + 1e-6
    edges = np.linspace(lo, hi, bins + 1)
    centers = (edges[:-1] + edges[1:]) / 2.0
    counts = np.zeros(bins)
    bin_size = (hi - lo) / bins

    highs = df["high"].values
    lows = df["low"].values
    vols = df["volume"].values
    for h, l, v in zip(highs, lows, vols):
        if v <= 0 or h < l:
            continue
        lo_idx = int(np.clip((l - lo) / bin_size, 0, bins - 1))
        hi_idx = int(np.clip((h - lo) / bin_size, 0, bins - 1))
        span = hi_idx - lo_idx + 1
        counts[lo_idx:hi_idx + 1] += v / span

    poc, vah, val = _value_area(centers, counts, va_pct)
    return ProfileResult(centers, counts, bin_size, poc, vah, val, counts.sum())


@dataclass
class MarketProfileResult:
    bin_centers: np.ndarray
    counts: np.ndarray                 # TPO count per price bin
    letters: list[str]                 # concatenated TPO letters per bin
    bin_size: float
    poc_price: float
    vah: float
    val: float
    ib_high: float
    ib_low: float
    single_prints: list[float] = field(default_factory=list)
    poor_high: bool = False
    poor_low: bool = False


def market_profile(df: pd.DataFrame, bins: int = 40, va_pct: float = 0.70,
                   tpo_minutes: int = 30) -> MarketProfileResult | None:
    """Build a TPO profile for the supplied (single-session) data."""
    if df is None or df.empty:
        return None
    lo = float(df["low"].min())
    hi = float(df["high"].max())
    if hi <= lo:
        hi = lo + 1e-6
    edges = np.linspace(lo, hi, bins + 1)
    centers = (edges[:-1] + edges[1:]) / 2.0
    bin_size = (hi - lo) / bins
    counts = np.zeros(bins)
    letters = ["" for _ in range(bins)]

    periods = df.resample(f"{tpo_minutes}min").agg(
        {"high": "max", "low": "min"}).dropna()
    ib_high = ib_low = None
    for i, (_, row) in enumerate(periods.iterrows()):
        letter = TPO_LETTERS[i % len(TPO_LETTERS)]
        lo_idx = int(np.clip((row["low"] - lo) / bin_size, 0, bins - 1))
        hi_idx = int(np.clip((row["high"] - lo) / bin_size, 0, bins - 1))
        for b in range(lo_idx, hi_idx + 1):
            counts[b] += 1
            letters[b] += letter
        if i == 0:
            ib_high, ib_low = row["high"], row["low"]
        elif i == 1:  # initial balance = first hour = first two 30m periods
            ib_high = max(ib_high, row["high"])
            ib_low = min(ib_low, row["low"])

    poc, vah, val = _value_area(centers, counts, va_pct)

    # single prints: bins inside the range touched by exactly one TPO
    single_prints = [float(centers[i]) for i in range(bins)
                     if 0 < counts[i] == 1]

    # poor high / low: two or more TPOs at the extreme bin (no tapering tail)
    poor_high = counts[-1] >= 2
    poor_low = counts[0] >= 2

    return MarketProfileResult(
        centers, counts, letters, bin_size, poc, vah, val,
        ib_high if ib_high is not None else hi,
        ib_low if ib_low is not None else lo,
        single_prints, poor_high, poor_low,
    )
