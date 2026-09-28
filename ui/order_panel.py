"""Paper-trading side panel: account summary, order entry, open orders,
positions and trade history. Reacts to PaperEngine signals and redraws order
lines / fill markers on the chart.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QComboBox, QDoubleSpinBox, QButtonGroup, QRadioButton, QTableWidget,
    QTableWidgetItem, QGroupBox, QHeaderView, QMessageBox,
)

from trading.orders import Order, BUY, SELL, MARKET, LIMIT, STOP, STOP_LIMIT

_TYPES = {"Market": MARKET, "Limit": LIMIT, "Stop": STOP, "Stop-Limit": STOP_LIMIT}


class OrderPanel(QWidget):
    def __init__(self, engine, chart):
        super().__init__()
        self.engine = engine
        self.chart = chart
        self.ticker = chart.ticker
        self.setMinimumWidth(300)
        self.setMaximumWidth(360)

        v = QVBoxLayout(self)
        self._build_account(v)
        self._build_order_entry(v)
        self._build_open_orders(v)
        self._build_positions(v)
        self._build_history(v)
        v.addStretch()

        engine.account_changed.connect(self.refresh_account)
        engine.position_changed.connect(self.refresh_positions)
        engine.position_changed.connect(self.refresh_account)
        engine.orders_changed.connect(self.refresh_orders)
        engine.orders_changed.connect(self.redraw_order_lines)
        engine.trade_closed.connect(lambda *_: self.refresh_history())
        engine.fill_event.connect(self._on_fill)

        self.refresh_all()

    def set_ticker(self, ticker):
        self.ticker = ticker
        self.refresh_all()

    # ------------------------------------------------------------------ account
    def _build_account(self, parent):
        box = QGroupBox("Account")
        g = QGridLayout(box)
        self.lbl = {}
        rows = [("Starting", "starting_balance"), ("Equity", "equity"),
                ("Realized P&L", "realized_pnl"), ("Unrealized", "unrealized_pnl"),
                ("Win rate", "win_rate"), ("Trades", "total_trades")]
        for i, (text, key) in enumerate(rows):
            g.addWidget(QLabel(text), i // 2, (i % 2) * 2)
            lab = QLabel("-")
            lab.setStyleSheet("font-weight:bold;")
            self.lbl[key] = lab
            g.addWidget(lab, i // 2, (i % 2) * 2 + 1)
        parent.addWidget(box)

    def refresh_account(self):
        s = self.engine.stats()
        self.lbl["starting_balance"].setText(f"${s['starting_balance']:,.2f}")
        self.lbl["equity"].setText(f"${s['equity']:,.2f}")
        self._set_pnl(self.lbl["realized_pnl"], s["realized_pnl"])
        self._set_pnl(self.lbl["unrealized_pnl"], s["unrealized_pnl"])
        self.lbl["win_rate"].setText(f"{s['win_rate']:.1f}%")
        self.lbl["total_trades"].setText(str(s["total_trades"]))

    def _set_pnl(self, label, value):
        color = "#26a69a" if value >= 0 else "#ef5350"
        label.setText(f"${value:,.2f}")
        label.setStyleSheet(f"font-weight:bold; color:{color};")

    # ------------------------------------------------------------------ entry
    def _build_order_entry(self, parent):
        box = QGroupBox("New Order")
        v = QVBoxLayout(box)

        side_row = QHBoxLayout()
        self.buy_btn = QRadioButton("BUY"); self.buy_btn.setChecked(True)
        self.sell_btn = QRadioButton("SELL")
        grp = QButtonGroup(self); grp.addButton(self.buy_btn); grp.addButton(self.sell_btn)
        self.buy_btn.setStyleSheet("color:#26a69a; font-weight:bold;")
        self.sell_btn.setStyleSheet("color:#ef5350; font-weight:bold;")
        side_row.addWidget(self.buy_btn); side_row.addWidget(self.sell_btn)
        v.addLayout(side_row)

        self.type_combo = QComboBox(); self.type_combo.addItems(_TYPES.keys())
        self.type_combo.currentTextChanged.connect(self._update_price_fields)
        v.addWidget(self.type_combo)

        self.qty = QDoubleSpinBox(); self.qty.setRange(0.0001, 1e6); self.qty.setValue(10)
        self.qty.setPrefix("Qty  ")
        v.addWidget(self.qty)

        self.limit = QDoubleSpinBox(); self.limit.setRange(0, 1e7); self.limit.setDecimals(2)
        self.limit.setPrefix("Limit  ")
        v.addWidget(self.limit)
        self.stop = QDoubleSpinBox(); self.stop.setRange(0, 1e7); self.stop.setDecimals(2)
        self.stop.setPrefix("Stop  ")
        v.addWidget(self.stop)

        submit = QPushButton("Submit Order")
        submit.clicked.connect(self._submit)
        v.addWidget(submit)
        row = QHBoxLayout()
        cancel = QPushButton("Cancel All"); cancel.clicked.connect(self._cancel_all)
        reset = QPushButton("Reset"); reset.clicked.connect(self._reset)
        row.addWidget(cancel); row.addWidget(reset)
        v.addLayout(row)
        parent.addWidget(box)
        self._update_price_fields()

    def _update_price_fields(self):
        t = _TYPES[self.type_combo.currentText()]
        self.limit.setVisible(t in (LIMIT, STOP_LIMIT))
        self.stop.setVisible(t in (STOP, STOP_LIMIT))

    def _submit(self):
        t = _TYPES[self.type_combo.currentText()]
        side = BUY if self.buy_btn.isChecked() else SELL
        order = Order(ticker=self.ticker, side=side, type=t, qty=self.qty.value(),
                      limit_price=self.limit.value() if self.limit.isVisible() else None,
                      stop_price=self.stop.value() if self.stop.isVisible() else None)
        self.engine.submit(order)

    def _cancel_all(self):
        self.engine.cancel_all(self.ticker)

    def _reset(self):
        if QMessageBox.question(self, "Reset", "Wipe all paper-trading history?") \
                == QMessageBox.Yes:
            self.engine.reset()
            self.chart.clear_markers()
            self.refresh_all()

    # ------------------------------------------------------------------ orders
    def _build_open_orders(self, parent):
        box = QGroupBox("Open Orders")
        v = QVBoxLayout(box)
        self.orders_tbl = QTableWidget(0, 3)
        self.orders_tbl.setHorizontalHeaderLabels(["Order", "Status", ""])
        self.orders_tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.orders_tbl.setMaximumHeight(130)
        v.addWidget(self.orders_tbl)
        parent.addWidget(box)

    def refresh_orders(self):
        orders = self.engine.open_orders(self.ticker)
        self.orders_tbl.setRowCount(len(orders))
        for i, o in enumerate(orders):
            self.orders_tbl.setItem(i, 0, QTableWidgetItem(o.describe()))
            self.orders_tbl.setItem(i, 1, QTableWidgetItem(o.status))
            btn = QPushButton("✕"); btn.clicked.connect(lambda _, o=o: self.engine.cancel(o))
            self.orders_tbl.setCellWidget(i, 2, btn)

    def redraw_order_lines(self):
        self.chart.clear_order_lines()
        for o in self.engine.open_orders(self.ticker):
            price = o.limit_price or o.stop_price
            if not price:
                continue
            color = "#26a69a" if o.side == BUY else "#ef5350"
            self.chart.add_order_line(price, o.describe(), color)

    # ------------------------------------------------------------------ positions
    def _build_positions(self, parent):
        box = QGroupBox("Positions")
        v = QVBoxLayout(box)
        self.pos_tbl = QTableWidget(0, 4)
        self.pos_tbl.setHorizontalHeaderLabels(["Sym", "Qty", "Avg", "P&L"])
        self.pos_tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.pos_tbl.setMaximumHeight(120)
        v.addWidget(self.pos_tbl)
        parent.addWidget(box)

    def refresh_positions(self):
        positions = [p for p in self.engine.positions.values() if not p.is_flat]
        self.pos_tbl.setRowCount(len(positions))
        for i, p in enumerate(positions):
            pnl, pct = self.engine.position_pnl(p.ticker)
            self.pos_tbl.setItem(i, 0, QTableWidgetItem(p.ticker))
            self.pos_tbl.setItem(i, 1, QTableWidgetItem(f"{p.qty:g}"))
            self.pos_tbl.setItem(i, 2, QTableWidgetItem(f"{p.avg_price:.2f}"))
            it = QTableWidgetItem(f"${pnl:,.2f} ({pct:+.2f}%)")
            it.setForeground(Qt.green if pnl >= 0 else Qt.red)
            self.pos_tbl.setItem(i, 3, it)

    # ------------------------------------------------------------------ history
    def _build_history(self, parent):
        box = QGroupBox("Trade History")
        v = QVBoxLayout(box)
        self.hist_tbl = QTableWidget(0, 5)
        self.hist_tbl.setHorizontalHeaderLabels(["Side", "Entry", "Exit", "P&L", "Qty"])
        self.hist_tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.hist_tbl.setMaximumHeight(160)
        v.addWidget(self.hist_tbl)
        parent.addWidget(box)

    def refresh_history(self):
        trades = self.engine.db.get_trades(self.ticker)
        self.hist_tbl.setRowCount(len(trades))
        for i, t in enumerate(reversed(trades)):
            self.hist_tbl.setItem(i, 0, QTableWidgetItem(t["side"]))
            self.hist_tbl.setItem(i, 1, QTableWidgetItem(f"{t['entry_price']:.2f}"))
            self.hist_tbl.setItem(i, 2, QTableWidgetItem(f"{t['exit_price']:.2f}"))
            it = QTableWidgetItem(f"${t['pnl']:,.2f}")
            it.setForeground(Qt.green if t["pnl"] >= 0 else Qt.red)
            self.hist_tbl.setItem(i, 3, it)
            self.hist_tbl.setItem(i, 4, QTableWidgetItem(f"{t['qty']:g}"))

    # ------------------------------------------------------------------ fills
    def _on_fill(self, order: Order):
        symbol = "t1" if order.side == BUY else "t"      # up / down triangle
        color = "#26a69a" if order.side == BUY else "#ef5350"
        self.chart.add_marker(order.filled_at, order.fill_price, symbol, color,
                              text=f"{order.side.upper()} {order.qty:g}")

    # ------------------------------------------------------------------ all
    def refresh_all(self):
        self.refresh_account()
        self.refresh_orders()
        self.redraw_order_lines()
        self.refresh_positions()
        self.refresh_history()
