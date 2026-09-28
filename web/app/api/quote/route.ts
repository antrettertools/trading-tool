import { NextRequest, NextResponse } from "next/server";
import { fetchLatestPrice } from "@/lib/fetcher";

export async function GET(request: NextRequest) {
  const symbol = request.nextUrl.searchParams.get("symbol")?.trim().toUpperCase();
  if (!symbol) {
    return NextResponse.json({ error: "symbol is required" }, { status: 400 });
  }
  const price = await fetchLatestPrice(symbol);
  return NextResponse.json(
    { symbol, price, ts: Date.now() / 1000 },
    { headers: { "Cache-Control": "no-store" } }
  );
}
