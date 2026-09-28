"""AMT Charting Tool — application entry point.

Assembles the main window: top bar (symbol / timeframe / live price ticker /
connection status), left drawing toolbar + indicator sidebar, central chart,
and a collapsible paper-trading panel on the right. Wires the live feed to the
chart's current candle and to the paper-trading engine.

Run:  python main.py
"""
from __future__ import annotations

import sys

import pandas as pd
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence, QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QLineEdit, QComboBox, QPushButton, QToolBar, QInputDialog, QSplitter,
    QStatusBar,
)

from config import load_config
from db.database import Database
from data import fetcher
from data.stream import LiveFeed
from data.fetcher import ALL_TIMEFRAMES
from chart.engine import ChartWidget
from ui.sidebar import Sidebar
from ui.order_panel import OrderPanel
from ui.journal import JournalManager, JournalDialog
from trading.paper import PaperEngine

# timeframe -> seconds per candle (None => calendar based)
_TF_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800,
               "1h": 3600, "4h": 14400, "1d": None, "1w": None}

_DRAW_TOOLS = [
    ("Horizontal line", "hline", "H"),
    ("Vertical line", "vline", "V"),
    ("Trend line", "trend", "T"),
    ("Ray", "ray", "R"),
    ("Extended line", "extended", "E"),
    ("Rectangle", "rect", "B"),
    ("Fib retracement", "fib", "F"),
    ("Fib extension", "fibext", "X"),
    ("Pitchfork", "pitchfork", "P"),
    ("Text label", "text", "L"),
]


def floor_timestamp(epoch: float, timeframe: str) -> pd.Timestamp:
    ts = pd.Timestamp(epoch, unit="s", tz="UTC")
    secs = _TF_SECONDS.get(timeframe)
    if secs:
        floored = (int(epoch) // secs) * secs
        return pd.Timestamp(floored, unit="s", tz="UTC")
    if timeframe == "1d":
        return ts.normalize()
    if timeframe == "1w":
        return (ts - pd.Timedelta(days=ts.weekday())).normalize()
    return ts


DARK_QSS = """
QMainWindow, QWidget { background:#131722; color:#d1d4dc; font-size:12px; }
QGroupBox { border:1px solid #2a2e39; border-radius:4px; margin-top:8px; padding-top:6px; }
QGroupBox::title { subcontrol-origin: margin; left:8px; color:#787b86; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit {
    background:#1e222d; border:1px solid #2a2e39; border-radius:3px; padding:3px; }
QPushButton { background:#2a2e39; border:1px solid #363a45; border-radius:3px; padding:4px 8px; }
QPushButton:hover { background:#363a45; }
QTableWidget { background:#1e222d; gridline-color:#2a2e39; }
QHeaderView::section { background:#1e222d; border:none; padding:3px; color:#787b86; }
QToolBar { background:#1e222d; border:none; spacing:2px; }
QScrollArea { border:none; }
QCheckBox { spacing:5px; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AMT Charting Tool")
        self.resize(1500, 900)

        self.config = load_config()
        self.db = Database()
        self.ticker = self.db.get_setting("ticker", self.config["default_ticker"])
        self.timeframe = self.db.get_setting("timeframe", self.config["default_timeframe"])
        self.last_price = None

        # core widgets
        self.chart = ChartWidget(self.config, self.db)
        self.engine = PaperEngine(self.db,
                                  self.config["paper_trading"]["starting_balance"])
        self.sidebar = Sidebar(self.chart, self.db)
        self.order_panel = OrderPanel(self.engine, self.chart)
        self.journal = JournalManager(self.chart, self.db)
        self.feed = LiveFeed(self.config)

        self._build_ui()
        self._wire()
        self.load_symbol(self.ticker, self.timeframe)

    # ------------------------------------------------------------------ ui
    def _build_ui(self):
        self.setStyleSheet(DARK_QSS)
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.addWidget(self._build_topbar())

        self.main_split = QSplitter(Qt.Horizontal)
        self.main_split.addWidget(self.sidebar)
        self.main_split.addWidget(self.chart)
        self.main_split.addWidget(self.order_panel)
        self.main_split.setStretchFactor(1, 1)
        self.main_split.setSizes([270, 950, 320])
        outer.addWidget(self.main_split, 1)

        self._build_draw_toolbar()
        self.setStatusBar(QStatusBar())

    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(4, 2, 4, 2)

        self.symbol_edit = QLineEdit(self.ticker)
        self.symbol_edit.setMaximumWidth(110)
        self.symbol_edit.returnPressed.connect(self._on_symbol_entered)
        h.addWidget(QLabel("Symbol:"))
        h.addWidget(self.symbol_edit)

        self.tf_combo = QComboBox()
        self.tf_combo.addItems(ALL_TIMEFRAMES)
        self.tf_combo.setCurrentText(self.timeframe)
        self.tf_combo.currentTextChanged.connect(self._on_tf_changed)
        h.addWidget(self.tf_combo)

        self.price_label = QLabel("—")
        self.price_label.setStyleSheet("font-size:18px; font-weight:bold;")
        h.addWidget(self.price_label)

        h.addStretch()
        self.conn_dot = QLabel("●")
        self.conn_dot.setStyleSheet("color:#ef5350; font-size:16px;")
        self.conn_text = QLabel("disconnected")
        self.conn_text.setStyleSheet("color:#787b86;")
        h.addWidget(self.conn_dot)
        h.addWidget(self.conn_text)

        toggle_orders = QPushButton("Trade Panel")
        toggle_orders.setCheckable(True); toggle_orders.setChecked(True)
        toggle_orders.toggled.connect(self.order_panel.setVisible)
        h.addWidget(toggle_orders)
        return bar

    def _build_draw_toolbar(self):
        tb = QToolBar("Drawing tools")
        tb.setOrientation(Qt.Vertical)
        self.addToolBar(Qt.LeftToolBarArea, tb)
        for label, kind, key in _DRAW_TOOLS:
            act = QAction(f"{label} ({key})", self)
            act.setShortcut(QKeySequence(key))
            act.triggered.connect(lambda _, k=kind: self._start_tool(k))
            tb.addAction(act)
        tb.addSeparator()
        delete = QAction("Delete selected (Del)", self)
        delete.setShortcut(QKeySequence(Qt.Key_Delete))
        delete.triggered.connect(self._delete_selected_drawing)
        tb.addAction(delete)
        clear = QAction("Clear all (Shift+Del)", self)
        clear.setShortcut(QKeySequence("Shift+Delete"))
        clear.triggered.connect(self.chart.drawings.clear)
        tb.addAction(clear)

    def _delete_selected_drawing(self):
        if self.chart.drawings.selected is None:
            self.statusBar().showMessage(
                "Click a drawing to select it, then press Delete", 3000)
            return
        self.chart.drawings.delete_selected()
        self.statusBar().showMessage("Drawing deleted", 2000)

    def _start_tool(self, kind):
        if kind == "text":
            self.chart.drawings.text_prompt = self._text_prompt
        self.chart.drawings.start_tool(kind)
        self.statusBar().showMessage(f"Drawing: {kind} — click on chart", 4000)

    def _text_prompt(self):
        text, ok = QInputDialog.getText(self, "Text label", "Enter text:")
        return text if ok else ""

    # ------------------------------------------------------------------ wiring
    def _wire(self):
        self.feed.price_tick.connect(self._on_price_tick)
        self.feed.status_changed.connect(self._on_status_changed)
        self.chart.candle_context.connect(self._on_journal_request)
        self.chart.request_indicator_menu.connect(
            lambda: self.statusBar().showMessage(
                "Use the sidebar to add indicators", 3000))

    # ------------------------------------------------------------------ symbol
    def _on_symbol_entered(self):
        sym = self.symbol_edit.text().strip().upper()
        if sym:
            self.load_symbol(sym, self.timeframe)

    def _on_tf_changed(self, tf):
        self.load_symbol(self.ticker, tf)

    def load_symbol(self, ticker: str, timeframe: str):
        self.statusBar().showMessage(f"Loading {ticker} {timeframe}…")
        QApplication.processEvents()
        df = fetcher.fetch(ticker, timeframe)
        if df is None or df.empty:
            self.statusBar().showMessage(
                f"No data for {ticker} {timeframe}", 5000)
            return
        self.ticker = ticker
        self.timeframe = timeframe
        self.symbol_edit.setText(ticker)
        self.chart.set_data(df, ticker, timeframe)
        self.chart.load_drawings()
        self.engine.load_ticker(ticker)
        self.order_panel.set_ticker(ticker)
        self.journal.set_ticker(ticker)
        self.db.set_setting("ticker", ticker)
        self.db.set_setting("timeframe", timeframe)
        self.last_price = float(df["close"].iloc[-1])
        self.price_label.setText(f"{self.last_price:.2f}")
        self.feed.start(ticker)
        self.statusBar().showMessage(f"{ticker} {timeframe} — {len(df)} candles", 4000)

    # ------------------------------------------------------------------ live
    def _on_price_tick(self, symbol, price, size, epoch):
        # update top-bar ticker with flash
        if self.last_price is not None:
            color = "#26a69a" if price >= self.last_price else "#ef5350"
            self.price_label.setStyleSheet(
                f"font-size:18px; font-weight:bold; color:{color};")
        self.price_label.setText(f"{price:.2f}")
        self.last_price = price

        self.engine.on_price(self.ticker, price)

        df = self.chart.df
        if df is None or df.empty:
            return
        bucket = floor_timestamp(epoch, self.timeframe)
        last_ts = df.index[-1]
        if bucket > last_ts:
            row = pd.Series({"open": price, "high": price, "low": price,
                             "close": price, "volume": size})
            self.chart.append_candle(bucket, row)
            self.journal.reload()
        else:
            r = df.iloc[-1].copy()
            r["close"] = price
            r["high"] = max(r["high"], price)
            r["low"] = min(r["low"], price)
            r["volume"] = r["volume"] + size
            self.chart.update_last_candle(r)

    def _on_status_changed(self, is_live, reason="" ):
        color = "#26a69a" if is_live else "#ef5350"
        self.conn_dot.setStyleSheet(f"color:{color}; font-size:16px;")
        self.conn_text.setText(reason or ("live (Alpaca)" if is_live
                                          else "polling (yfinance)"))
        self.conn_text.setToolTip(self.conn_text.text())

    # ------------------------------------------------------------------ journal
    def _on_journal_request(self, global_pos, ts_epoch, price):
        dlg = JournalDialog(self, price, ts_epoch, self.db.get_trades(self.ticker))
        if dlg.exec() and dlg.note:
            self.journal.add_note(ts_epoch, price, dlg.note, dlg.trade_id)

    # ------------------------------------------------------------------ close
    def closeEvent(self, event):
        self.feed.stop()
        self.db.set_setting("splitter", self.main_split.sizes())
        self.db.set_setting("chart_splitter", self.chart.splitter.sizes())
        super().closeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        sizes = self.db.get_setting("splitter")
        if sizes:
            self.main_split.setSizes(sizes)
        csizes = self.db.get_setting("chart_splitter")
        if csizes:
            self.chart.splitter.setSizes(csizes)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("AMT Charting Tool")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
