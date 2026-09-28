// AMT overlay calculations: prior-period value areas, session open, overnight
// range, naked POC detection. Direct port of ../chart/overlays.py.
import type { Candle } from "./types";
import { volumeProfile } from "./profiles";

export type PeriodFreq = "day" | "week" | "month";

function periodKey(epochSeconds: number, freq: PeriodFreq): number {
  const d = new Date(epochSeconds * 1000);
  if (freq === "day") return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
  if (freq === "month") return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1);
  // week: Monday-anchored, matching pandas Grouper(freq='W-MON')-like behavior
  const day = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
  const weekday = (day.getUTCDay() + 6) % 7; // 0 = Monday
  day.setUTCDate(day.getUTCDate() - weekday);
  return day.getTime();
}

function periodGroups(candles: Candle[], freq: PeriodFreq): Candle[][] {
  const map = new Map<number, Candle[]>();
  const order: number[] = [];
  for (const c of candles) {
    const key = periodKey(c.time, freq);
    if (!map.has(key)) {
      map.set(key, []);
      order.push(key);
    }
    map.get(key)!.push(c);
  }
  order.sort((a, b) => a - b);
  return order.map((k) => map.get(k)!);
}

export interface PriorPeriodLevels {
  vah: number;
  val: number;
  poc: number;
}

export function priorPeriodLevels(
  candles: Candle[],
  freq: PeriodFreq,
  bins = 40,
  vaPct = 0.7
): PriorPeriodLevels | null {
  const groups = periodGroups(candles, freq);
  if (groups.length < 2) return null;
  const sub = groups[groups.length - 2]; // second-to-last completed period
  const prof = volumeProfile(sub, bins, vaPct);
  if (!prof) return null;
  return { vah: prof.vah, val: prof.val, poc: prof.poc };
}

export function sessionOpen(candles: Candle[]): number | null {
  const groups = periodGroups(candles, "day");
  if (!groups.length) return null;
  return groups[groups.length - 1][0].open;
}

export interface OvernightRange {
  high: number;
  low: number;
}

export function overnightRange(
  candles: Candle[],
  rthStartHourUtc = 13,
  rthEndHourUtc = 20
): OvernightRange | null {
  const groups = periodGroups(candles, "day");
  if (!groups.length) return null;
  const sub = groups[groups.length - 1];
  const on = sub.filter((c) => {
    const hour = new Date(c.time * 1000).getUTCHours();
    return hour < rthStartHourUtc || hour >= rthEndHourUtc;
  });
  if (!on.length) return null;
  return {
    high: Math.max(...on.map((c) => c.high)),
    low: Math.min(...on.map((c) => c.low)),
  };
}

// x-index positions (row offsets) where a new UTC day begins.
export function sessionBoundaries(candles: Candle[]): number[] {
  const boundaries: number[] = [];
  let prevDay: number | null = null;
  candles.forEach((c, i) => {
    const day = Math.floor(c.time / 86400);
    if (prevDay !== null && day !== prevDay) boundaries.push(i);
    prevDay = day;
  });
  return boundaries;
}

export function nakedPocs(candles: Candle[], freq: PeriodFreq = "day", bins = 40, lookback = 20): number[] {
  const groups = periodGroups(candles, freq);
  if (groups.length < 2) return [];
  const recent = groups.slice(-(lookback + 1));
  const naked: number[] = [];
  for (let gi = 0; gi < recent.length - 1; gi++) {
    const sub = recent[gi];
    const prof = volumeProfile(sub, bins);
    if (!prof) continue;
    const poc = prof.poc;
    const afterStart = sub[sub.length - 1].time;
    const later = candles.filter((c) => c.time > afterStart);
    const touched = later.some((c) => c.low <= poc && c.high >= poc);
    if (!touched) naked.push(poc);
  }
  return naked;
}
