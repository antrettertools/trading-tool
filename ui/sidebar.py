"""Left sidebar: indicator, overlay and profile toggles.

Talks directly to the ChartWidget (set_indicator / set_overlay / set_profile_mode
/ set_market_profile). The full control state is persisted to the database
(setting key ``sidebar_state``) on every change and restored on startup, so
indicator selections survive between sessions. Because the chart keeps its
indicator config internally, restoring before data is loaded is fine — the
indicators are drawn once set_data runs.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QSpinBox,
    QDoubleSpinBox, QComboBox, QPushButton, QColorDialog, QScrollArea,
    QGroupBox, QFrame,
)

_MA_COLORS = ["#42a5f5", "#ffb74d", "#ab47bc", "#26c6da", "#ec407a"]
_OVERLAYS = [("Prev day VA", "prev_day"), ("Prev week VA", "prev_week"),
             ("Prev month VA", "prev_month"), ("Session open", "session_open"),
             ("Overnight range", "overnight"), ("Naked POC", "naked_poc")]


class ColorButton(QPushButton):
    def __init__(self, color="#42a5f5"):
        super().__init__()
        self.setFixedSize(22, 22)
        self._color = color
        self._apply()
        self.clicked.connect(self._pick)

    def _apply(self):
        self.setStyleSheet(
            f"background:{self._color}; border:1px solid #555; border-radius:3px;")

    def _pick(self):
        c = QColorDialog.getColor(QColor(self._color), self)
        if c.isValid():
            self._color = c.name()
            self._apply()
            if self._on_change:
                self._on_change()

    _on_change = None

    @property
    def color(self):
        return self._color


class Sidebar(QScrollArea):
    def __init__(self, chart, db):
        super().__init__()
        self.chart = chart
        self.db = db
        self._loading = True
        self.setWidgetResizable(True)
        self.setMinimumWidth(250)
        self.setMaximumWidth(310)
        container = QWidget()
        self.setWidget(container)
        self.v = QVBoxLayout(container)
        self.v.setAlignment(Qt.AlignTop)
        self._ma_rows: list = []
        self.controls: dict = {}

        self._build_moving_averages()
        self._build_momentum()
        self._build_volatility()
        self._build_volume()
        self._build_profiles()
        self._build_overlays()
        self._build_sessions()

        self._loading = False
        self._restore_state()

    # ------------------------------------------------------------------ helpers
    def _group(self, title) -> QVBoxLayout:
        box = QGroupBox(title)
        lay = QVBoxLayout(box)
        lay.setSpacing(4)
        self.v.addWidget(box)
        return lay

    def _checkbox(self, layout, text, slot, key=None):
        cb = QCheckBox(text)
        cb.toggled.connect(slot)
        cb.toggled.connect(lambda *_: self._persist())
        layout.addWidget(cb)
        if key:
            self.controls[key] = cb
        return cb

    def _persist(self):
        if self._loading:
            return
        self.db.set_setting("sidebar_state", self._collect_state())

    # ------------------------------------------------------------------ MAs
    def _build_moving_averages(self):
        self.ma_layout = self._group("Moving Averages")
        add = QPushButton("+ Add MA")
        add.clicked.connect(lambda: self._add_ma_row())
        self.ma_layout.addWidget(add)

    def _add_ma_row(self, kind="EMA", period=20, color=None, checked=True):
        row = QFrame()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        cb = QCheckBox(); cb.setChecked(checked)
        combo = QComboBox(); combo.addItems(["EMA", "SMA"])
        combo.setCurrentText(kind)
        spin = QSpinBox(); spin.setRange(1, 500); spin.setValue(period)
        color = color or _MA_COLORS[len(self._ma_rows) % len(_MA_COLORS)]
        colbtn = ColorButton(color)
        wspin = QDoubleSpinBox(); wspin.setRange(0.5, 5); wspin.setValue(1.5)
        wspin.setSingleStep(0.5); wspin.setFixedWidth(50)
        rm = QPushButton("✕"); rm.setFixedWidth(24)
        for w in (cb, combo, spin, colbtn, wspin, rm):
            h.addWidget(w)
        self.ma_layout.addWidget(row)

        state = {"name": None, "row": row, "cb": cb, "combo": combo,
                 "spin": spin, "colbtn": colbtn, "wspin": wspin}
        self._ma_rows.append(state)

        def apply():
            if state["name"]:
                self.chart.set_indicator(state["name"], False)
                state["name"] = None
            if cb.isChecked():
                name = f"{combo.currentText()}{spin.value()}"
                state["name"] = name
                self.chart.set_indicator(name, True, {
                    "period": spin.value(), "color": colbtn.color,
                    "width": wspin.value()})
            self._persist()

        def remove():
            if state["name"]:
                self.chart.set_indicator(state["name"], False)
            row.setParent(None)
            if state in self._ma_rows:
                self._ma_rows.remove(state)
            self._persist()

        colbtn._on_change = apply
        cb.toggled.connect(apply)
        combo.currentTextChanged.connect(apply)
        spin.valueChanged.connect(apply)
        wspin.valueChanged.connect(apply)
        rm.clicked.connect(remove)
        apply()

    # ------------------------------------------------------------------ momentum
    def _build_momentum(self):
        lay = self._group("Momentum")
        h = QHBoxLayout()
        self.rsi_cb = QCheckBox("RSI")
        self.rsi_period = QSpinBox(); self.rsi_period.setRange(2, 100)
        self.rsi_period.setValue(14)
        h.addWidget(self.rsi_cb); h.addWidget(self.rsi_period); h.addStretch()
        lay.addLayout(h)
        self.rsi_cb.toggled.connect(self._apply_rsi)
        self.rsi_period.valueChanged.connect(self._apply_rsi)
        self._checkbox(lay, "MACD (12,26,9)",
                       lambda on: self.chart.set_indicator("MACD", on), key="macd")

    def _apply_rsi(self, *_):
        self.chart.set_indicator("RSI", self.rsi_cb.isChecked(),
                                 {"period": self.rsi_period.value()})
        self._persist()

    # ------------------------------------------------------------------ volatility
    def _build_volatility(self):
        lay = self._group("Volatility")
        h = QHBoxLayout()
        self.bb_cb = QCheckBox("Bollinger")
        self.bb_period = QSpinBox(); self.bb_period.setRange(2, 100)
        self.bb_period.setValue(20)
        self.bb_mult = QDoubleSpinBox(); self.bb_mult.setRange(0.5, 5)
        self.bb_mult.setValue(2.0); self.bb_mult.setSingleStep(0.5)
        h.addWidget(self.bb_cb); h.addWidget(self.bb_period)
        h.addWidget(self.bb_mult); h.addStretch()
        lay.addLayout(h)
        self.bb_cb.toggled.connect(self._apply_bb)
        self.bb_period.valueChanged.connect(self._apply_bb)
        self.bb_mult.valueChanged.connect(self._apply_bb)
        self._checkbox(lay, "ATR label",
                       lambda on: self.chart.set_indicator("ATR", on), key="atr")

    def _apply_bb(self, *_):
        self.chart.set_indicator("Bollinger", self.bb_cb.isChecked(),
                                 {"period": self.bb_period.value(),
                                  "mult": self.bb_mult.value()})
        self._persist()

    # ------------------------------------------------------------------ volume
    def _build_volume(self):
        lay = self._group("Volume")
        self.vwap_bands = QCheckBox("VWAP std-dev bands"); self.vwap_bands.setChecked(True)
        self.vwap_cb = self._checkbox(lay, "VWAP (session)", self._apply_vwap, key="vwap")
        lay.addWidget(self.vwap_bands)
        self.vwap_bands.toggled.connect(self._apply_vwap)
        self._checkbox(lay, "Volume MA (20)",
                       lambda on: self.chart.set_indicator("VolumeMA", on,
                                                           {"period": 20}), key="volma")

    def _apply_vwap(self, *_):
        self.chart.set_indicator("VWAP", self.vwap_cb.isChecked(),
                                 {"bands": self.vwap_bands.isChecked()})
        self._persist()

    # ------------------------------------------------------------------ profiles
    def _build_profiles(self):
        lay = self._group("Profiles")
        lay.addWidget(QLabel("Volume Profile"))
        self.vp_mode = QComboBox()
        self.vp_mode.addItems(["Off", "Visible range", "Last 3 sessions"])
        self.vp_mode.currentIndexChanged.connect(self._vp_changed)
        lay.addWidget(self.vp_mode)
        self._checkbox(lay, "Market Profile (TPO, daily)",
                       lambda on: self.chart.set_market_profile(on), key="mp")

    def _vp_changed(self, idx):
        self.chart.set_profile_mode({0: None, 1: "visible", 2: "sessions"}[idx])
        self._persist()

    # ------------------------------------------------------------------ overlays
    def _build_overlays(self):
        lay = self._group("AMT Overlays")
        for label, key in _OVERLAYS:
            self._checkbox(lay, label,
                           lambda on, k=key: self.chart.set_overlay(k, on),
                           key=f"ov_{key}")

    # ------------------------------------------------------------------ sessions
    def _build_sessions(self):
        lay = self._group("Session / Time")
        self._checkbox(lay, "Session separators",
                       lambda on: self.chart.set_overlay("sessions", on),
                       key="ov_sessions")

    # ------------------------------------------------------------------ state
    def _collect_state(self) -> dict:
        return {
            "ma": [{"kind": s["combo"].currentText(), "period": s["spin"].value(),
                    "color": s["colbtn"].color, "checked": s["cb"].isChecked()}
                   for s in self._ma_rows],
            "rsi": {"on": self.rsi_cb.isChecked(), "period": self.rsi_period.value()},
            "bb": {"on": self.bb_cb.isChecked(), "period": self.bb_period.value(),
                   "mult": self.bb_mult.value()},
            "vwap": {"on": self.vwap_cb.isChecked(), "bands": self.vwap_bands.isChecked()},
            "vp_mode": self.vp_mode.currentIndex(),
            "checks": {k: cb.isChecked() for k, cb in self.controls.items()},
        }

    def _restore_state(self):
        state = self.db.get_setting("sidebar_state")
        if not state:
            return
        self._loading = True
        try:
            for ma in state.get("ma", []):
                self._add_ma_row(kind=ma.get("kind", "EMA"),
                                 period=ma.get("period", 20),
                                 color=ma.get("color"),
                                 checked=ma.get("checked", True))
            rsi = state.get("rsi", {})
            self.rsi_period.setValue(rsi.get("period", 14))
            self.rsi_cb.setChecked(rsi.get("on", False))
            bb = state.get("bb", {})
            self.bb_period.setValue(bb.get("period", 20))
            self.bb_mult.setValue(bb.get("mult", 2.0))
            self.bb_cb.setChecked(bb.get("on", False))
            vwap = state.get("vwap", {})
            self.vwap_bands.setChecked(vwap.get("bands", True))
            self.vwap_cb.setChecked(vwap.get("on", False))
            for k, val in state.get("checks", {}).items():
                if k in self.controls:
                    self.controls[k].setChecked(val)
            self.vp_mode.setCurrentIndex(state.get("vp_mode", 0))
        finally:
            self._loading = False
        # apply everything now that controls reflect saved state
        self._apply_rsi(); self._apply_bb(); self._apply_vwap()
