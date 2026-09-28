import { NextRequest, NextResponse } from "next/server";
import { fetchCandles, TIMEFRAMES } from "@/lib/fetcher";
import type { Timeframe } from "@/lib/types";

export async function GET(request: NextRequest) {
  const symbol = request.nextUrl.searchParams.get("symbol")?.trim().toUpperCase();
  const timeframe = request.nextUrl.searchParams.get("timeframe") as Timeframe | null;
  if (!symbol) {
    return NextResponse.json({ error: "symbol is required" }, { status: 400 });
  }
  if (!timeframe || !(timeframe in TIMEFRAMES)) {
    return NextResponse.json({ error: "invalid timeframe" }, { status: 400 });
  }
  const candles = await fetchCandles(symbol, timeframe);
  const ttl = TIMEFRAMES[timeframe].ttlSeconds;
  return NextResponse.json(
    { symbol, timeframe, candles },
    { headers: { "Cache-Control": `s-maxage=${ttl}, stale-while-revalidate` } }
  );
}
