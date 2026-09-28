# AMT Charting Tool

A personal **Auction Market Theory** charting and paper-trading desktop app,
styled like TradingView. Built with PySide6 + PyQtGraph. Historical data comes
from **yfinance**; live prices stream from the free **Alpaca** paper-trading
WebSocket (with a yfinance polling fallback).

> Personal research/education tool. Paper trading is fully simulated — no real
> orders are ever sent to a broker.

---

## Features

- **Chart engine** — high-performance candlesticks, resizable volume panel,
  crosshair with price/time, scroll-to-zoom (time axis), drag-to-pan,
  auto-scaling price axis, OHLCV hover readout, right-click context menu.
- **Live feed** — Alpaca real-time IEX trades update the current candle tick by
  tick; a new candle rolls over automatically at each timeframe boundary. Green
  dot = live WebSocket, red dot = polling/disconnected. Top-bar price ticker
  flashes green/red on up/down ticks.
- **Volume Profile** — horizontal bars, POC (yellow), VAH/VAL dashed lines,
  shaded value area, configurable bins / value-area %. Modes: visible range or
  last N sessions; recalculates live.
- **Market Profile (TPO)** — letter blocks per 30-min period, Initial Balance
  high/low, TPO-count value area, single prints, poor high/low detection.
- **Indicators** — SMA/EMA (multiple, configurable), RSI (sub-panel), MACD
  (sub-panel with histogram), Bollinger Bands (shaded), ATR label, session
  VWAP with SD bands, Volume MA, session separators.
- **AMT overlays** — previous day/week/month VAH/VAL/POC, session open,
  overnight range, naked POC detection.
- **Drawing tools** — horizontal/vertical/trend/ray/extended lines, rectangle,
  Fibonacci retracement & extension, Andrews pitchfork, text labels. Editable,
  deletable, saved per ticker/timeframe. Keyboard shortcuts (H/V/T/R/E/B/F/X/P/L).
- **Paper trading** — market/limit/stop/stop-limit orders matched against the
  live feed, order lines + fill markers on the chart, positions with live P&L,
  trade history, account summary (equity, realized/unrealized P&L, win rate).
  Persists in SQLite; Reset button wipes history.
- **Journal** — right-click a candle → add a timestamped note (optionally linked
  to a trade); notes appear as clickable flags.
- **Persistence** — drawings, panel layout, and last symbol/timeframe restored
  between sessions via SQLite.

---

## Setup

Requires **Python 3.11+** (tested on 3.12). Works on Windows, macOS, Linux.

```bash
# from the project folder
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate

pip install -r requirements.txt
```

### Configure

Copy the template and add your keys:

```bash
# Windows
copy config.example.json config.json
# macOS/Linux
cp config.example.json config.json
```

Then edit `config.json`:

- `alpaca.api_key` / `alpaca.api_secret` — your **paper** keys (see below)
- `default_ticker`, `default_timeframe`
- `paper_trading.starting_balance`
- `theme` colors

If the Alpaca keys are left as placeholders, the app still runs — it just falls
back to polling yfinance for live prices (interval set by
`polling_interval_seconds` in config.json, default 5s; futures/forex always
use polling since Alpaca's free feed is US equities only).

### Getting a free Alpaca paper API key

1. Sign up at <https://alpaca.markets/> (free).
2. Log in and switch to **Paper Trading** (toggle in the dashboard).
3. Open **Home → API Keys** (or *Generate New Keys*) in the paper account.
4. Copy the **API Key ID** and **Secret Key** into `config.json` under
   `alpaca.api_key` / `alpaca.api_secret`.
5. Keep `base_url` as `https://paper-api.alpaca.markets` and `feed` as `iex`
   (the free real-time feed).

The secret is shown only once — regenerate if you lose it.

---

## Run

```bash
python main.py
```

- Type a symbol in the top bar and press Enter: stocks/ETFs (`SPY`, `AAPL`),
  futures (`ES=F`), forex (`EURUSD=X`). Pick a timeframe from the dropdown.
- Use the left sidebar to toggle indicators, profiles and AMT overlays.
- Use the left toolbar (or keyboard shortcuts) for drawing tools.
- Toggle the **Trade Panel** button to show/hide paper trading.

> **Live data note:** Alpaca's real-time WebSocket only serves US
> equities/ETFs. Futures and forex symbols automatically use the yfinance
> polling fallback. Outside US market hours there may be no live trades — the
> chart still renders full history.

---

## Project structure

```
main.py                 app entry point + MainWindow
config.py               config.json loading / defaults
config.json             your settings + Alpaca keys (gitignored)
config.example.json     template
requirements.txt
data/
  fetcher.py            yfinance historical OHLCV + on-disk cache
  stream.py             Alpaca WebSocket live feed + polling fallback
chart/
  engine.py             PyQtGraph rendering (candles, volume, sub-panels, crosshair)
  indicators.py         SMA/EMA/RSI/MACD/Bollinger/ATR/VWAP/VolumeMA
  profiles.py           Volume Profile + Market Profile (TPO)
  overlays.py           AMT overlays (prior-period VA, naked POC, sessions)
  drawings.py           drawing tools + DrawingManager
trading/
  orders.py             order model + fill logic
  paper.py              paper-trading engine (matching, positions, P&L)
ui/
  sidebar.py            indicator/overlay/profile toggles
  order_panel.py        paper-trading UI
  journal.py            journal dialog + flag markers
db/
  database.py           all SQLite storage
```

Data is cached in `.cache/`; all state lives in `amt_app.db` (SQLite).
