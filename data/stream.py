"""Live price feed.

Primary source is the Alpaca real-time WebSocket (free IEX feed) via alpaca-py,
running in a background thread. If Alpaca keys are missing, the symbol is not a
US equity Alpaca supports, or the socket drops, we fall back to polling yfinance
every ``polling_interval_seconds``.

Emits Qt signals so the GUI thread can update safely:
    price_tick(symbol, price, size, epoch_seconds)
    status_changed(is_live_websocket)
"""
from __future__ import annotations

import logging
import threading
import time

from PySide6.QtCore import QObject, Signal, QTimer

from data import fetcher

# alpaca-py retries a failed auth ("connection limit exceeded") forever and logs
# a full traceback each time; we detect the failure ourselves and fall back, so
# keep its logger quiet.
logging.getLogger("alpaca").setLevel(logging.CRITICAL)


def _is_alpaca_equity(symbol: str) -> bool:
    # Alpaca's stock stream only handles plain US equity/ETF tickers, e.g. SPY,
    # AAPL. Futures (ES=F), forex (EURUSD=X) and indices (^GSPC) are not alpha.
    return symbol.isalpha()


class LiveFeed(QObject):
    price_tick = Signal(str, float, float, float)
    # (is_live_websocket, human-readable reason/mode shown in the UI)
    status_changed = Signal(bool, str)

    def __init__(self, config):
        super().__init__()
        self._config = config
        self._symbol: str | None = None
        self._running = False
        self._mode = "idle"          # 'alpaca' | 'polling' | 'idle'
        self._stream = None
        self._ws_thread: threading.Thread | None = None
        self._poll_thread: threading.Thread | None = None
        self._alpaca_timer: QTimer | None = None
        # incremented on every start(); background threads capture their token
        # so stale threads from a previous symbol can't update the UI
        self._session = 0

    # ------------------------------------------------------------------ control
    def start(self, symbol: str):
        self.stop()
        self._symbol = symbol
        self._running = True
        self._session += 1
        token = self._session
        if self._config.has_alpaca_keys and _is_alpaca_equity(symbol):
            self._start_alpaca(symbol, token)
        elif not self._config.has_alpaca_keys:
            self._start_polling(symbol, token, "polling - no Alpaca keys set")
        else:
            self._start_polling(
                symbol, token,
                "polling - Alpaca live feed is US equities only (not futures/forex)")

    def stop(self):
        self._running = False
        self._mode = "idle"
        self._session += 1   # invalidate any in-flight background threads
        if self._alpaca_timer is not None:
            self._alpaca_timer.stop()
            self._alpaca_timer = None
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:
                pass
            self._stream = None
        # threads are daemonic and exit on the _running flag / socket close
        self._ws_thread = None
        self._poll_thread = None

    def _active(self, token) -> bool:
        return self._running and token == self._session

    def _emit(self, symbol, price, size, ts, token):
        if self._active(token):
            self.price_tick.emit(symbol, float(price), float(size or 0), float(ts))

    # ------------------------------------------------------------------ alpaca
    def _start_alpaca(self, symbol: str, token: int):
        self._mode = "alpaca"

        def run():
            try:
                from alpaca.data.live import StockDataStream
                from alpaca.data.enums import DataFeed
                a = self._config.alpaca
                feed = {"iex": DataFeed.IEX, "sip": DataFeed.SIP}.get(
                    a.get("feed", "iex").lower(), DataFeed.IEX)
                stream = StockDataStream(a["api_key"], a["api_secret"], feed=feed)
                self._stream = stream

                async def on_trade(trade):
                    ts = getattr(trade, "timestamp", None)
                    epoch = ts.timestamp() if ts else time.time()
                    self._emit(symbol, trade.price,
                               getattr(trade, "size", 0), epoch, token)

                stream.subscribe_trades(on_trade, symbol)
                # NOTE: do NOT report "live" here — subscribe only registers a
                # callback. The actual connect+auth happens inside run(); a
                # watcher confirms it below before we say we're live.
                stream.run()  # blocks until stop() or fatal error
            except Exception as exc:
                if self._active(token):
                    print(f"[stream] Alpaca feed error: {exc}")
            finally:
                if self._active(token) and self._mode == "alpaca":
                    self._start_polling(symbol, token,
                                        "polling - Alpaca disconnected")

        self._ws_thread = threading.Thread(target=run, daemon=True)
        self._ws_thread.start()
        self._watch_alpaca(symbol, token)

    def _watch_alpaca(self, symbol: str, token: int, timeout: float = 10.0):
        """Confirm the websocket actually authenticated (alpaca-py sets
        ``stream._running`` only after a successful connect+auth). If it doesn't
        connect within ``timeout`` (e.g. free-tier 'connection limit exceeded',
        which alpaca-py otherwise retries forever), abort and poll instead."""
        timer = QTimer()
        self._alpaca_timer = timer
        started = time.time()

        def check():
            if not self._active(token):
                timer.stop()
                return
            stream = self._stream
            if stream is not None and getattr(stream, "_running", False):
                timer.stop()
                self.status_changed.emit(True, "live (Alpaca)")   # genuinely live
                return
            if time.time() - started > timeout:
                timer.stop()
                print("[stream] Alpaca did not connect (likely 'connection limit "
                      "exceeded' - the free tier allows only one live stream, and "
                      "a previous session may still be open). Using polling.")
                self._fallback_from_alpaca(symbol, token)

        timer.timeout.connect(check)
        timer.start(500)

    def _fallback_from_alpaca(self, symbol: str, token: int):
        if not self._active(token):
            return
        self._mode = "polling"   # stops the ws thread's finally re-triggering
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
            except Exception:
                pass
        self._start_polling(symbol, token, "polling - Alpaca unavailable")

    # ------------------------------------------------------------------ polling
    def _start_polling(self, symbol: str, token: int,
                       reason: str = "polling (yfinance)"):
        self._mode = "polling"
        if self._active(token):
            self.status_changed.emit(False, reason)
        base = max(3, int(self._config.get("polling_interval_seconds", 5)))

        def run():
            wait = base
            while self._active(token) and self._mode == "polling":
                price = fetcher.latest_price(symbol)
                if price is not None:
                    self._emit(symbol, price, 0, time.time(), token)
                    wait = base                  # data flowing -> full speed
                else:
                    wait = min(wait * 2, 30)     # back off if Yahoo returns nothing
                # sleep in 0.5s slices so stop() stays responsive
                slept = 0.0
                while slept < wait and self._active(token) and self._mode == "polling":
                    time.sleep(0.5)
                    slept += 0.5

        self._poll_thread = threading.Thread(target=run, daemon=True)
        self._poll_thread.start()
