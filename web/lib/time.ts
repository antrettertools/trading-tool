// Bucket an epoch-seconds timestamp to the start of its timeframe candle.
// Port of main.py's floor_timestamp, used to decide whether a polled tick
// starts a new candle or updates the current one.
import type { Timeframe } from "./types";

const TF_SECONDS: Partial<Record<Timeframe, number>> = {
  "1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400,
};

export function floorTimestamp(epoch: number, timeframe: Timeframe): number {
  const secs = TF_SECONDS[timeframe];
  if (secs) return Math.floor(epoch / secs) * secs;
  if (timeframe === "1d") return Math.floor(epoch / 86400) * 86400;
  if (timeframe === "1w") {
    const dayStart = Math.floor(epoch / 86400) * 86400;
    const weekday = (Math.floor(dayStart / 86400) + 4) % 7; // 1970-01-01 was a Thursday
    return dayStart - weekday * 86400;
  }
  return epoch;
}
