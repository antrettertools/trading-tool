// Server-side historical OHLCV retrieval from Yahoo Finance's public chart
// endpoint — the same data source the desktop app's yfinance dependency
// wraps. Port of ../data/fetcher.py's TIMEFRAMES table and normalize/resample
// logic (4h is synthesized by resampling 1h, same as the desktop app).
import type { Candle, Timeframe } from "./types";

interface TimeframeConfig {
  yahooInterval: string;
  lookbackDays: number;
  ttlSeconds: number;
  resampleToSeconds?: number;
}

export const TIMEFRAMES: Record<Timeframe, TimeframeConfig> = {
  "1m": { yahooInterval: "1m", lookbackDays: 7, ttlSeconds: 60 },
  "5m": { yahooInterval: "5m", lookbackDays: 60, ttlSeconds: 120 },
  "15m": { yahooInterval: "15m", lookbackDays: 60, ttlSeconds: 300 },
  "30m": { yahooInterval: "30m", lookbackDays: 60, ttlSeconds: 300 },
  "1h": { yahooInterval: "60m", lookbackDays: 730, ttlSeconds: 600 },
  "4h": { yahooInterval: "60m", lookbackDays: 730, ttlSeconds: 600, resampleToSeconds: 4 * 3600 },
  "1d": { yahooInterval: "1d", lookbackDays: 365 * 20, ttlSeconds: 1800 },
  "1w": { yahooInterval: "1wk", lookbackDays: 365 * 20, ttlSeconds: 3600 },
};

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36";

interface YahooChartResult {
  timestamp?: number[];
  indicators?: {
    quote?: Array<{
      open?: (number | null)[];
      high?: (number | null)[];
      low?: (number | null)[];
      close?: (number | null)[];
      volume?: (number | null)[];
    }>;
  };
}

async function fetchYahooChart(
  symbol: string,
  interval: string,
  lookbackDays: number
): Promise<YahooChartResult | null> {
  const now = Math.floor(Date.now() / 1000);
  const period1 = now - lookbackDays * 86400;
  const url =
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}` +
    `?interval=${interval}&period1=${period1}&period2=${now}&includePrePost=false`;
  const res = await fetch(url, { headers: { "User-Agent": UA }, cache: "no-store" });
  if (!res.ok) return null;
  const json = await res.json();
  const result = json?.chart?.result?.[0];
  return result ?? null;
}

function normalize(result: YahooChartResult | null): Candle[] {
  if (!result?.timestamp || !result.indicators?.quote?.[0]) return [];
  const q = result.indicators.quote[0];
  const ts = result.timestamp;
  const out: Candle[] = [];
  let lastOpen: number | null = null;
  let lastHigh: number | null = null;
  let lastLow: number | null = null;
  let lastClose: number | null = null;
  for (let i = 0; i < ts.length; i++) {
    const o = q.open?.[i] ?? null;
    const h = q.high?.[i] ?? null;
    const l = q.low?.[i] ?? null;
    const c = q.close?.[i] ?? null;
    const v = q.volume?.[i] ?? 0;
    // forward-fill price gaps, same as fetcher.py's _normalize
    const open: number | null = o ?? lastOpen;
    const high: number | null = h ?? lastHigh;
    const low: number | null = l ?? lastLow;
    const close: number | null = c ?? lastClose;
    if (close == null) continue; // no data yet to ffill from
    lastOpen = open;
    lastHigh = high;
    lastLow = low;
    lastClose = close;
    out.push({
      time: ts[i],
      open: open as number,
      high: high as number,
      low: low as number,
      close: close as number,
      volume: v ?? 0,
    });
  }
  return out;
}

function resample(candles: Candle[], bucketSeconds: number): Candle[] {
  if (candles.length === 0) return candles;
  const buckets = new Map<number, Candle>();
  const order: number[] = [];
  for (const c of candles) {
    const bucketTime = Math.floor(c.time / bucketSeconds) * bucketSeconds;
    const existing = buckets.get(bucketTime);
    if (!existing) {
      buckets.set(bucketTime, { time: bucketTime, open: c.open, high: c.high, low: c.low, close: c.close, volume: c.volume });
      order.push(bucketTime);
    } else {
      existing.high = Math.max(existing.high, c.high);
      existing.low = Math.min(existing.low, c.low);
      existing.close = c.close;
      existing.volume += c.volume;
    }
  }
  return order.sort((a, b) => a - b).map((t) => buckets.get(t)!);
}

export async function fetchCandles(symbol: string, timeframe: Timeframe): Promise<Candle[]> {
  const cfg = TIMEFRAMES[timeframe];
  if (!cfg) throw new Error(`Unsupported timeframe: ${timeframe}`);
  let candles: Candle[];
  try {
    const result = await fetchYahooChart(symbol, cfg.yahooInterval, cfg.lookbackDays);
    candles = normalize(result);
  } catch {
    return [];
  }
  if (cfg.resampleToSeconds) candles = resample(candles, cfg.resampleToSeconds);
  return candles;
}

// Quick last-price lookup for the polling feed. Port of fetcher.latest_price:
// try a short 1m-interval window first, fall back to progressively coarser
// windows if the market/asset has no fresh intraday data.
export async function fetchLatestPrice(symbol: string): Promise<number | null> {
  const attempts: Array<[string, number]> = [
    ["1m", 1],
    ["5m", 5],
    ["1d", 5],
  ];
  for (const [interval, days] of attempts) {
    try {
      const result = await fetchYahooChart(symbol, interval, days);
      const candles = normalize(result);
      if (candles.length > 0) return candles[candles.length - 1].close;
    } catch {
      // try the next fallback
    }
  }
  return null;
}
