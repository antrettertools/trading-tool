// Volume Profile and Market Profile (TPO) calculations. Direct port of
// ../chart/profiles.py. Pure data computations; rendering happens in
// components/Chart.tsx via a canvas primitive.
import type { Candle } from "./types";

export interface ProfileResult {
  binCenters: number[];
  counts: number[];
  binSize: number;
  poc: number;
  vah: number;
  val: number;
  total: number;
}

function valueArea(centers: number[], counts: number[], vaPct: number): [number, number, number] {
  const total = counts.reduce((s, v) => s + v, 0);
  if (total <= 0) return [centers[0], centers[0], centers[centers.length - 1]];
  let pocIdx = 0;
  for (let i = 1; i < counts.length; i++) if (counts[i] > counts[pocIdx]) pocIdx = i;
  const target = total * vaPct;
  let included = counts[pocIdx];
  let lo = pocIdx;
  let hi = pocIdx;
  const n = counts.length;
  while (included < target && (lo > 0 || hi < n - 1)) {
    const below = lo > 0 ? counts[lo - 1] : -1;
    const above = hi < n - 1 ? counts[hi + 1] : -1;
    if (above >= below) {
      hi += 1;
      included += counts[hi];
    } else {
      lo -= 1;
      included += counts[lo];
    }
  }
  return [centers[pocIdx], centers[hi], centers[lo]];
}

export function volumeProfile(candles: Candle[], bins = 40, vaPct = 0.7): ProfileResult | null {
  if (!candles.length) return null;
  let lo = Infinity;
  let hi = -Infinity;
  for (const c of candles) {
    lo = Math.min(lo, c.low);
    hi = Math.max(hi, c.high);
  }
  if (hi <= lo) hi = lo + 1e-6;
  const binSize = (hi - lo) / bins;
  const centers = Array.from({ length: bins }, (_, i) => lo + binSize * (i + 0.5));
  const counts = new Array(bins).fill(0);
  for (const c of candles) {
    if (c.volume <= 0 || c.high < c.low) continue;
    const loIdx = Math.min(Math.max(Math.floor((c.low - lo) / binSize), 0), bins - 1);
    const hiIdx = Math.min(Math.max(Math.floor((c.high - lo) / binSize), 0), bins - 1);
    const span = hiIdx - loIdx + 1;
    for (let b = loIdx; b <= hiIdx; b++) counts[b] += c.volume / span;
  }
  const [poc, vah, val] = valueArea(centers, counts, vaPct);
  return { binCenters: centers, counts, binSize, poc, vah, val, total: counts.reduce((s, v) => s + v, 0) };
}

export interface MarketProfileResult {
  binCenters: number[];
  counts: number[];
  letters: string[];
  binSize: number;
  poc: number;
  vah: number;
  val: number;
  ibHigh: number;
  ibLow: number;
  singlePrints: number[];
  poorHigh: boolean;
  poorLow: boolean;
}

const TPO_LETTERS =
  "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";

export function marketProfile(
  candles: Candle[],
  bins = 40,
  vaPct = 0.7,
  tpoMinutes = 30
): MarketProfileResult | null {
  if (!candles.length) return null;
  let lo = Infinity;
  let hi = -Infinity;
  for (const c of candles) {
    lo = Math.min(lo, c.low);
    hi = Math.max(hi, c.high);
  }
  if (hi <= lo) hi = lo + 1e-6;
  const binSize = (hi - lo) / bins;
  const centers = Array.from({ length: bins }, (_, i) => lo + binSize * (i + 0.5));
  const counts = new Array(bins).fill(0);
  const letters: string[] = new Array(bins).fill("");

  const periodSeconds = tpoMinutes * 60;
  const periods = new Map<number, { high: number; low: number }>();
  for (const c of candles) {
    const bucket = Math.floor(c.time / periodSeconds) * periodSeconds;
    const p = periods.get(bucket);
    if (!p) periods.set(bucket, { high: c.high, low: c.low });
    else {
      p.high = Math.max(p.high, c.high);
      p.low = Math.min(p.low, c.low);
    }
  }
  const orderedPeriods = [...periods.entries()].sort((a, b) => a[0] - b[0]);
  let ibHigh: number | null = null;
  let ibLow: number | null = null;
  orderedPeriods.forEach(([, row], i) => {
    const letter = TPO_LETTERS[i % TPO_LETTERS.length];
    const loIdx = Math.min(Math.max(Math.floor((row.low - lo) / binSize), 0), bins - 1);
    const hiIdx = Math.min(Math.max(Math.floor((row.high - lo) / binSize), 0), bins - 1);
    for (let b = loIdx; b <= hiIdx; b++) {
      counts[b] += 1;
      letters[b] += letter;
    }
    if (i === 0) {
      ibHigh = row.high;
      ibLow = row.low;
    } else if (i === 1) {
      ibHigh = Math.max(ibHigh!, row.high);
      ibLow = Math.min(ibLow!, row.low);
    }
  });

  const [poc, vah, val] = valueArea(centers, counts, vaPct);
  const singlePrints = centers.filter((_, i) => counts[i] === 1);
  const poorHigh = counts[counts.length - 1] >= 2;
  const poorLow = counts[0] >= 2;

  return {
    binCenters: centers,
    counts,
    letters,
    binSize,
    poc,
    vah,
    val,
    ibHigh: ibHigh ?? hi,
    ibLow: ibLow ?? lo,
    singlePrints,
    poorHigh,
    poorLow,
  };
}
