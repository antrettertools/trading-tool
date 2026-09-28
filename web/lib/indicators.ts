// Pure indicator calculations over an array of candles, aligned index-for-
// index with the input. Direct port of ../chart/indicators.py.
import type { Candle } from "./types";

export function sma(candles: Candle[], period: number): number[] {
  const closes = candles.map((c) => c.close);
  const out = new Array(closes.length).fill(NaN);
  let sum = 0;
  for (let i = 0; i < closes.length; i++) {
    sum += closes[i];
    const windowSize = Math.min(period, i + 1);
    if (i >= period) sum -= closes[i - period];
    out[i] = sum / windowSize;
  }
  return out;
}

export function ema(candles: Candle[], period: number): number[] {
  const closes = candles.map((c) => c.close);
  const out = new Array(closes.length).fill(NaN);
  const k = 2 / (period + 1);
  let prev = closes[0];
  for (let i = 0; i < closes.length; i++) {
    prev = i === 0 ? closes[0] : closes[i] * k + prev * (1 - k);
    out[i] = prev;
  }
  return out;
}

// Wilder-style EMA with alpha = 1/period, matching pandas .ewm(alpha=1/period)
function wilderEwm(values: number[], period: number, minPeriods: number): number[] {
  const alpha = 1 / period;
  const out = new Array(values.length).fill(NaN);
  let prev = 0;
  let count = 0;
  for (let i = 0; i < values.length; i++) {
    if (Number.isNaN(values[i])) continue;
    count++;
    prev = count === 1 ? values[i] : values[i] * alpha + prev * (1 - alpha);
    out[i] = count >= minPeriods ? prev : NaN;
  }
  return out;
}

export function rsi(candles: Candle[], period = 14): number[] {
  const closes = candles.map((c) => c.close);
  const gains: number[] = [NaN];
  const losses: number[] = [NaN];
  for (let i = 1; i < closes.length; i++) {
    const delta = closes[i] - closes[i - 1];
    gains.push(Math.max(delta, 0));
    losses.push(Math.max(-delta, 0));
  }
  const avgGain = wilderEwm(gains, period, period);
  const avgLoss = wilderEwm(losses, period, period);
  return avgGain.map((g, i) => {
    const l = avgLoss[i];
    if (Number.isNaN(g) || Number.isNaN(l)) return 50;
    if (l === 0) return g === 0 ? 50 : 100;
    const rs = g / l;
    return 100 - 100 / (1 + rs);
  });
}

function ewmFull(values: number[], span: number): number[] {
  const k = 2 / (span + 1);
  const out = new Array(values.length).fill(NaN);
  let prev = values[0];
  for (let i = 0; i < values.length; i++) {
    prev = i === 0 ? values[0] : values[i] * k + prev * (1 - k);
    out[i] = prev;
  }
  return out;
}

export function macd(candles: Candle[], fast = 12, slow = 26, signal = 9) {
  const closes = candles.map((c) => c.close);
  const fastEma = ewmFull(closes, fast);
  const slowEma = ewmFull(closes, slow);
  const macdLine = fastEma.map((v, i) => v - slowEma[i]);
  const signalLine = ewmFull(macdLine, signal);
  const hist = macdLine.map((v, i) => v - signalLine[i]);
  return { macdLine, signalLine, hist };
}

export function bollinger(candles: Candle[], period = 20, mult = 2.0) {
  const closes = candles.map((c) => c.close);
  const mid = sma(candles, period);
  const upper = new Array(closes.length).fill(NaN);
  const lower = new Array(closes.length).fill(NaN);
  for (let i = 0; i < closes.length; i++) {
    const start = Math.max(0, i - period + 1);
    const windowVals = closes.slice(start, i + 1);
    const mean = mid[i];
    const variance = windowVals.reduce((s, v) => s + (v - mean) ** 2, 0) / windowVals.length;
    const std = Math.sqrt(variance);
    upper[i] = mean + mult * std;
    lower[i] = mean - mult * std;
  }
  return { upper, mid, lower };
}

export function atr(candles: Candle[], period = 14): number[] {
  const tr: number[] = candles.map((c, i) => {
    if (i === 0) return c.high - c.low;
    const prevClose = candles[i - 1].close;
    return Math.max(c.high - c.low, Math.abs(c.high - prevClose), Math.abs(c.low - prevClose));
  });
  return wilderEwm(tr, period, 1);
}

function sessionKey(epochSeconds: number): number {
  return Math.floor(epochSeconds / 86400) * 86400; // UTC-day bucket
}

export function vwap(candles: Candle[], withBands = true) {
  const n = candles.length;
  const vw = new Array(n).fill(NaN);
  const upper1 = new Array(n).fill(NaN);
  const lower1 = new Array(n).fill(NaN);
  const upper2 = new Array(n).fill(NaN);
  const lower2 = new Array(n).fill(NaN);
  let sess = -1;
  let cumTpv = 0;
  let cumVol = 0;
  let cumTp2v = 0;
  let lastVol = 1;
  for (let i = 0; i < n; i++) {
    const c = candles[i];
    const key = sessionKey(c.time);
    if (key !== sess) {
      sess = key;
      cumTpv = 0;
      cumVol = 0;
      cumTp2v = 0;
    }
    const tp = (c.high + c.low + c.close) / 3;
    const vol = c.volume > 0 ? c.volume : lastVol;
    lastVol = vol;
    cumTpv += tp * vol;
    cumVol += vol;
    cumTp2v += tp * tp * vol;
    const v = cumTpv / cumVol;
    vw[i] = v;
    if (withBands) {
      const variance = Math.max(cumTp2v / cumVol - v * v, 0);
      const std = Math.sqrt(variance);
      upper1[i] = v + std;
      lower1[i] = v - std;
      upper2[i] = v + 2 * std;
      lower2[i] = v - 2 * std;
    }
  }
  return { vwap: vw, upper1, lower1, upper2, lower2 };
}

export function volumeMa(candles: Candle[], period = 20): number[] {
  const vols = candles.map((c) => c.volume);
  const out = new Array(vols.length).fill(NaN);
  let sum = 0;
  for (let i = 0; i < vols.length; i++) {
    sum += vols[i];
    const windowSize = Math.min(period, i + 1);
    if (i >= period) sum -= vols[i - period];
    out[i] = sum / windowSize;
  }
  return out;
}
