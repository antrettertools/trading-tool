"""Journal: add timestamped notes on candles, shown as flag markers.

A note is created via right-click -> "Add journal note" on the chart, stored in
SQLite per ticker, and rendered as a clickable flag. Clicking a flag shows the
note text. Notes can optionally be linked to a paper trade id.
"""
from __future__ import annotations

import time

import pandas as pd
import pyqtgraph as pg
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QPlainTextEdit, QDialogButtonBox, QLabel, QComboBox,
    QMenu,
)


class JournalDialog(QDialog):
    def __init__(self, parent, price, ts, trades=None):
        super().__init__(parent)
        self.setWindowTitle("Journal Note")
        self.setMinimumWidth(340)
        v = QVBoxLayout(self)
        v.addWidget(QLabel(
            f"{pd.Timestamp(ts, unit='s', tz='UTC').strftime('%Y-%m-%d %H:%M')}"
            f"   @ {price:.2f}"))
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("Write your note…")
        v.addWidget(self.text)
        self.trade_combo = None
        if trades:
            v.addWidget(QLabel("Link to trade (optional):"))
            self.trade_combo = QComboBox()
            self.trade_combo.addItem("— none —", None)
            for t in trades:
                self.trade_combo.addItem(
                    f"#{t['id']} {t['side']} {t['pnl']:+.2f}", t["id"])
            v.addWidget(self.trade_combo)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        v.addWidget(bb)

    @property
    def note(self):
        return self.text.toPlainText().strip()

    @property
    def trade_id(self):
        return self.trade_combo.currentData() if self.trade_combo else None


class JournalManager:
    def __init__(self, chart, db):
        self.chart = chart
        self.db = db
        self.ticker = chart.ticker
        self.scatter = pg.ScatterPlotItem(symbol="t2", size=16,
                                          brush=pg.mkBrush("#ffca28"),
                                          pen=pg.mkPen("k"))
        self.scatter.sigClicked.connect(self._on_click)
        self.chart.price_plot.addItem(self.scatter)
        self._notes_by_point = {}

    def set_ticker(self, ticker):
        self.ticker = ticker
        self.reload()

    def add_note(self, ts_epoch, price, note, trade_id=None):
        if not note:
            return
        self.db.add_journal(self.ticker, ts_epoch, price, note, trade_id)
        self.reload()

    def reload(self):
        notes = self.db.get_journal(self.ticker)
        df = self.chart.df
        spots = []
        self._notes_by_point = {}
        if df is None or df.empty:
            self.scatter.setData([])
            return
        for n in notes:
            ts = pd.Timestamp(n["ts"], unit="s", tz="UTC")
            idx = df.index.get_indexer([ts], method="nearest")
            if idx[0] == -1:
                continue
            i = int(idx[0])
            price = n["price"] if n["price"] is not None else float(df["high"].iloc[i])
            spots.append({"pos": (i, price), "data": n})
        self.scatter.setData(spots)

    def _on_click(self, scatter, points):
        if not points:
            return
        n = points[0].data()
        menu = QMenu()
        preview = n["note"] if len(n["note"]) <= 60 else n["note"][:60] + "…"
        info = menu.addAction(preview)
        info.setEnabled(False)
        if n.get("trade_id"):
            link = menu.addAction(f"(linked to trade #{n['trade_id']})")
            link.setEnabled(False)
        menu.addSeparator()
        menu.addAction("Delete note", lambda: self._delete(n["id"]))
        menu.exec(QCursor.pos())

    def _delete(self, note_id):
        self.db.delete_journal(note_id)
        self.reload()
