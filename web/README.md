# AMT Charting Tool — Web

A browser-based port of the [PySide6 desktop app](../README.md) one directory
up: Auction Market Theory charting and paper-trading, deployable on Vercel.
Built with Next.js (App Router) and [lightweight-charts](https://tradingview.github.io/lightweight-charts/)
(TradingView's own open-source charting library).

## What's different from the desktop app

The desktop app is a native Qt GUI with a local SQLite database and an
Alpaca WebSocket feed — none of that runs on a serverless web host. This port
keeps the same look and feature set with web-appropriate equivalents:

| Desktop app | Web app |
|---|---|
| yfinance historical data | Yahoo Finance's public chart endpoint, called from a server route (`app/api/candles`) |
| Alpaca WebSocket + yfinance polling fallback | Polling only (`app/api/quote`), same backoff behavior as the desktop app's own fallback |
| SQLite (`amt_app.db`) | Browser `localStorage` (`lib/storage.ts`) — state is per-browser, not synced across devices |
| PyQtGraph drawing tools (10 tools) | Core subset in v1: horizontal/vertical/trend line, rectangle, text label. Fibonacci retracement/extension and Andrews pitchfork are a planned fast-follow |

Every indicator, the volume/market profile math, the AMT overlays, and the
paper-trading fill/P&L engine are direct logic ports — see the file-level
comments in `lib/` for which Python module each one replaces.

## Local development

```bash
npm install
cp .env.example .env.local   # no keys required; see comments in the file
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Deploying on Vercel

1. Push this repository to GitHub (the repo root, not just `web/`).
2. In Vercel, "Add New Project" → import the repo.
3. Set **Root Directory** to `web` (Vercel auto-detects Next.js from there).
4. No environment variables are required for the default setup.

## Project layout

```
app/
  page.tsx, layout.tsx        shell (renders the client-only AppShell)
  api/candles, api/quote      server routes for historical/live price data
components/                   Chart, Sidebar, OrderPanel, DrawingLayer, etc.
lib/                          ported math (indicators/profiles/overlays/orders/
                               paperEngine), fetcher, storage, types
```
