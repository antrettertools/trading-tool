// Non-secret app defaults. Port of the defaults in ../config.py — with the
// Alpaca keys gone (see ../.env.example), there's nothing sensitive left
// here, so this is a plain checked-in constant instead of an env var.
export const config = {
  defaultTicker: "SPY",
  defaultTimeframe: "1d" as const,
  startingBalance: 10000,
  pollingIntervalSeconds: Number(process.env.NEXT_PUBLIC_POLLING_INTERVAL_SECONDS ?? 5),
};
