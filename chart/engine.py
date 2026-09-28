"""PyQtGraph chart engine.

Renders candlesticks on an index-based x-axis (so weekend gaps don't leave
holes) with a custom time axis that maps indices back to timestamps. Volume,
RSI and MACD live in their own linked plots inside a vertical QSplitter so the
dividers are user-resizable. The widget is the central coordinator: it owns the
indicator curves, profile items, AMT overlays, drawings and trade/journal
markers, exposing toggle methods the UI calls.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal, QPointF, QTimer
from PySide6.QtGui import QPicture, QPainter, QColor, QPen, QBrush
from PySide6.QtWidgets import QSplitter, QVBoxLayout, QWidget, QMenu

from chart import indicators as ind
from chart import profiles as prof
from chart import overlays as ov
from chart.drawings import DrawingManager


# --------------------------------------------------------------------------- #
#  Custom graphics items                                                      #
# --------------------------------------------------------------------------- #
class CandlestickItem(pg.GraphicsObject):
    """Draws all candles into a cached QPicture for speed."""

    def __init__(self, up_color: str, down_color: str):
        super().__init__()
        self._picture = QPicture()
        self._data = None  # (N,5) o,h,l,c arrays via DataFrame
        self.up = QColor(up_color)
        self.down = QColor(down_color)
        self.width = 0.7

    def set_data(self, df: pd.DataFrame):
        self._data = df
        self._generate()

    def _generate(self):
        self._picture = QPicture()
        if self._data is None or self._data.empty:
            self.informViewBoundsChanged()
            self.update()
            return
        p = QPainter(self._picture)
        o = self._data["open"].values
        h = self._data["high"].values
        l = self._data["low"].values
        c = self._data["close"].values
        w = self.width / 2.0
        up_pen = QPen(self.up); up_pen.setCosmetic(True)
        dn_pen = QPen(self.down); dn_pen.setCosmetic(True)
        up_brush = QBrush(self.up)
        dn_brush = QBrush(self.down)
        for i in range(len(o)):
            rising = c[i] >= o[i]
            p.setPen(up_pen if rising else dn_pen)
            p.setBrush(up_brush if rising else dn_brush)
            # wick
            p.drawLine(QPointF(i, l[i]), QPointF(i, h[i]))
            # body
            top = max(o[i], c[i])
            bot = min(o[i], c[i])
            if top == bot:
                top += 1e-9
            p.drawRect(pg.QtCore.QRectF(i - w, bot, w * 2, top - bot))
        p.end()
        self.informViewBoundsChanged()
        self.prepareGeometryChange()
        self.update()

    def paint(self, p, *args):
        self._picture.play(p)

    def boundingRect(self):
        if self._data is None or self._data.empty:
            return pg.QtCore.QRectF()
        n = len(self._data)
        lo = float(self._data["low"].min())
        hi = float(self._data["high"].max())
        return pg.QtCore.QRectF(-1, lo, n + 1, hi - lo)


class VolumeBarItem(pg.GraphicsObject):
    def __init__(self, up_color: str, down_color: str):
        super().__init__()
        self._picture = QPicture()
        self._data = None
        self.up = QColor(up_color); self.up.setAlpha(130)
        self.down = QColor(down_color); self.down.setAlpha(130)
        self.width = 0.7

    def set_data(self, df: pd.DataFrame):
        self._data = df
        self._generate()

    def _generate(self):
        self._picture = QPicture()
        if self._data is None or self._data.empty:
            self.update(); return
        p = QPainter(self._picture)
        o = self._data["open"].values
        c = self._data["close"].values
        v = self._data["volume"].values
        w = self.width / 2.0
        for i in range(len(v)):
            color = self.up if c[i] >= o[i] else self.down
            p.setPen(QPen(color))
            p.setBrush(QBrush(color))
            p.drawRect(pg.QtCore.QRectF(i - w, 0, w * 2, v[i]))
        p.end()
        self.prepareGeometryChange()
        self.update()

    def paint(self, p, *args):
        self._picture.play(p)

    def boundingRect(self):
        if self._data is None or self._data.empty:
            return pg.QtCore.QRectF()
        n = len(self._data)
        vmax = float(self._data["volume"].max() or 1)
        return pg.QtCore.QRectF(-1, 0, n + 1, vmax)


class TimeAxisItem(pg.AxisItem):
    """Maps integer candle indices to timestamp strings."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._timestamps: pd.DatetimeIndex | None = None
        self._fmt = "%Y-%m-%d"

    def set_timestamps(self, ts: pd.DatetimeIndex, fmt: str):
        self._timestamps = ts
        self._fmt = fmt

    def tickStrings(self, values, scale, spacing):
        if self._timestamps is None or len(self._timestamps) == 0:
            return [""] * len(values)
        out = []
        n = len(self._timestamps)
        for v in values:
            i = int(round(v))
            if 0 <= i < n:
                out.append(self._timestamps[i].strftime(self._fmt))
            else:
                out.append("")
        return out


_AXIS_FMT = {
    "1m": "%H:%M", "5m": "%H:%M", "15m": "%H:%M", "30m": "%H:%M",
    "1h": "%m-%d %H:%M", "4h": "%m-%d %H:%M", "1d": "%Y-%m-%d", "1w": "%Y-%m-%d",
}


# --------------------------------------------------------------------------- #
#  Chart widget                                                               #
# --------------------------------------------------------------------------- #
class ChartWidget(QWidget):
    candle_context = Signal(object, float, float)   # (QPoint global, ts, price)
    request_indicator_menu = Signal()

    def __init__(self, config, db):
        super().__init__()
        self.config = config
        self.db = db
        self.theme = config.theme
        self.df: pd.DataFrame | None = None
        self.ticker = config["default_ticker"]
        self.timeframe = config["default_timeframe"]

        self._indicator_items: dict[str, list] = {}
        self._overlay_items: list = []
        self._profile_items: list = []
        self._marker_items: list = []
        self._order_line_items: list = []
        self._indicator_cfg: dict = {}
        self._profile_mode = None       # None | 'visible' | 'sessions' | 'range'
        self._mp_enabled = False

        pg.setConfigOptions(antialias=True, background=self.theme["background"],
                            foreground=self.theme["text"])
        self._build_ui()

    # ------------------------------------------------------------------ build
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.splitter = QSplitter(Qt.Vertical)
        layout.addWidget(self.splitter)

        grid = self.theme["grid"]

        self.time_axis = TimeAxisItem(orientation="bottom")
        self.price_plot = pg.PlotWidget(axisItems={"bottom": self.time_axis})
        self.price_vb = self.price_plot.getViewBox()
        self.price_vb.setMouseMode(pg.ViewBox.PanMode)
        self.price_plot.showGrid(x=True, y=True, alpha=0.2)
        self.price_plot.setLabel("right", "Price")
        self.price_plot.showAxis("right")
        self.price_plot.hideAxis("left")
        self.splitter.addWidget(self.price_plot)

        self.volume_plot = pg.PlotWidget()
        self.volume_plot.setXLink(self.price_plot)
        self.volume_plot.showGrid(x=True, y=True, alpha=0.2)
        self.volume_plot.showAxis("right"); self.volume_plot.hideAxis("left")
        self.volume_plot.setLabel("right", "Vol")
        self.volume_plot.setMaximumHeight(160)
        self.splitter.addWidget(self.volume_plot)

        self.rsi_plot = pg.PlotWidget()
        self.rsi_plot.setXLink(self.price_plot)
        self.rsi_plot.showAxis("right"); self.rsi_plot.hideAxis("left")
        self.rsi_plot.setLabel("right", "RSI")
        self.rsi_plot.setMaximumHeight(140)
        self.rsi_plot.setYRange(0, 100)
        self.splitter.addWidget(self.rsi_plot)
        self.rsi_plot.hide()

        self.macd_plot = pg.PlotWidget()
        self.macd_plot.setXLink(self.price_plot)
        self.macd_plot.showAxis("right"); self.macd_plot.hideAxis("left")
        self.macd_plot.setLabel("right", "MACD")
        self.macd_plot.setMaximumHeight(140)
        self.splitter.addWidget(self.macd_plot)
        self.macd_plot.hide()

        self.splitter.setSizes([600, 150, 0, 0])

        # candles + volume items
        self.candle_item = CandlestickItem(self.theme["candle_up"],
                                           self.theme["candle_down"])
        self.price_plot.addItem(self.candle_item)
        self.volume_item = VolumeBarItem(self.theme["candle_up"],
                                         self.theme["candle_down"])
        self.volume_plot.addItem(self.volume_item)

        # crosshair
        pen = pg.mkPen(self.theme["text"], width=1, style=Qt.DashLine)
        self.v_line = pg.InfiniteLine(angle=90, movable=False, pen=pen)
        self.h_line = pg.InfiniteLine(angle=0, movable=False, pen=pen)
        self.price_plot.addItem(self.v_line, ignoreBounds=True)
        self.price_plot.addItem(self.h_line, ignoreBounds=True)
        self.vol_vline = pg.InfiniteLine(angle=90, movable=False, pen=pen)
        self.volume_plot.addItem(self.vol_vline, ignoreBounds=True)

        # hover OHLCV label
        self.ohlc_label = pg.TextItem(anchor=(0, 0), color=self.theme["text"])
        self.price_plot.addItem(self.ohlc_label, ignoreBounds=True)
        self.price_label = pg.TextItem(anchor=(0, 0.5),
                                       color=self.theme["background"],
                                       fill=pg.mkBrush(self.theme["accent"]))
        self.price_plot.addItem(self.price_label, ignoreBounds=True)

        # auto y-scale on x range change; disable manual y drag/zoom
        self.price_vb.setMouseEnabled(x=True, y=False)
        self.volume_plot.getViewBox().setMouseEnabled(x=True, y=False)
        self.price_plot.sigRangeChanged.connect(self._auto_range_y)

        # debounced redraw of a visible-range volume profile while panning/zooming
        self._profile_timer = QTimer(self)
        self._profile_timer.setSingleShot(True)
        self._profile_timer.setInterval(120)
        self._profile_timer.timeout.connect(self._refresh_visible_profile)
        self.price_vb.sigXRangeChanged.connect(self._on_x_range_changed)

        # mouse + context menu
        self.price_plot.scene().sigMouseMoved.connect(self._on_mouse_move)
        self.price_plot.setMenuEnabled(False)
        self.price_plot.scene().contextMenu = None
        self.price_vb.menu = None
        self.price_plot.scene().sigMouseClicked.connect(self._on_click)

        # drawing manager (price plot)
        self.drawings = DrawingManager(self.price_plot, self.theme,
                                       self._index_to_x_dt)
        self.drawings.changed.connect(self._save_drawings)

    # ------------------------------------------------------------------ data
    def set_data(self, df: pd.DataFrame, ticker: str, timeframe: str,
                 keep_view: bool = False):
        self.ticker = ticker
        self.timeframe = timeframe
        self.df = df
        self.candle_item.set_data(df)
        self.volume_item.set_data(df)
        fmt = _AXIS_FMT.get(timeframe, "%Y-%m-%d")
        self.time_axis.set_timestamps(df.index, fmt)
        if not keep_view and not df.empty:
            n = len(df)
            start = max(0, n - 150)
            self.price_plot.setXRange(start, n + 5, padding=0)
        self.drawings.set_context(ticker, timeframe)
        self.refresh_indicators()
        self.refresh_overlays()
        self.refresh_profile()
        self._auto_range_y()

    def update_last_candle(self, row: pd.Series):
        """Live update: mutate the final candle and redraw cheaply."""
        if self.df is None or self.df.empty:
            return
        self.df.iloc[-1] = row
        self.candle_item.set_data(self.df)
        self.volume_item.set_data(self.df)
        # refresh live-sensitive overlays/indicators lightly
        if "VWAP" in self._indicator_cfg:
            self.refresh_indicators(only={"VWAP"})
        if self._profile_mode:
            self.refresh_profile()

    def append_candle(self, ts, row: pd.Series):
        if self.df is None:
            return
        self.df.loc[ts] = row
        self.set_data(self.df, self.ticker, self.timeframe, keep_view=True)

    # ------------------------------------------------------------------ x/profile
    def _on_x_range_changed(self, *args):
        # only a visible-range volume profile needs to follow the viewport
        if self._profile_mode == "visible":
            self._profile_timer.start()

    def _refresh_visible_profile(self):
        if self._profile_mode == "visible":
            self.refresh_profile()

    # ------------------------------------------------------------------ y auto
    def _auto_range_y(self, *args):
        if self.df is None or self.df.empty:
            return
        (x0, x1), _ = self.price_vb.viewRange()
        i0 = max(0, int(np.floor(x0)))
        i1 = min(len(self.df), int(np.ceil(x1)))
        if i1 <= i0:
            return
        win = self.df.iloc[i0:i1]
        lo = float(win["low"].min())
        hi = float(win["high"].max())
        if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
            return
        pad = (hi - lo) * 0.08
        self.price_vb.setYRange(lo - pad, hi + pad, padding=0)
        vmax = float(win["volume"].max() or 1)
        self.volume_plot.getViewBox().setYRange(0, vmax * 1.1, padding=0)

    # ------------------------------------------------------------------ mouse
    def _on_mouse_move(self, pos):
        if self.df is None or self.df.empty:
            return
        if not self.price_plot.sceneBoundingRect().contains(pos):
            return
        mp = self.price_vb.mapSceneToView(pos)
        x, y = mp.x(), mp.y()
        self.v_line.setPos(x)
        self.h_line.setPos(y)
        self.vol_vline.setPos(x)
        i = int(round(x))
        if 0 <= i < len(self.df):
            r = self.df.iloc[i]
            ts = self.df.index[i]
            self.ohlc_label.setText(
                f"{ts.strftime('%Y-%m-%d %H:%M')}   "
                f"O {r.open:.2f}  H {r.high:.2f}  L {r.low:.2f}  "
                f"C {r.close:.2f}  V {int(r.volume):,}")
            (vx0, vx1), (vy0, vy1) = self.price_vb.viewRange()
            self.ohlc_label.setPos(vx0, vy1)
        self.price_label.setText(f"{y:.2f}")
        (vx0, vx1), _ = self.price_vb.viewRange()
        self.price_label.setPos(vx1, y)

    def _on_click(self, ev):
        if self.df is None or self.df.empty:
            return
        pos = ev.scenePos()
        if not self.price_plot.sceneBoundingRect().contains(pos):
            return
        mp = self.price_vb.mapSceneToView(pos)
        # let active drawing tool consume the click first
        if self.drawings.active_tool:
            self.drawings.handle_click(mp.x(), mp.y())
            ev.accept()
            return
        drawing = self._drawing_at(pos)
        if ev.button() == Qt.LeftButton:
            # click a drawing to select it; click empty space to deselect
            self.drawings.select(drawing)
            if drawing is not None:
                ev.accept()
            return
        if ev.button() == Qt.RightButton:
            self.drawings.select(drawing)
            i = int(round(mp.x()))
            ts = self.df.index[max(0, min(i, len(self.df) - 1))]
            self._show_context_menu(ev.screenPos(), ts, mp.y(), drawing)
            ev.accept()

    def _to_px(self, x, y):
        p = self.price_vb.mapViewToScene(QPointF(x, y))
        return p.x(), p.y()

    def _drawing_at(self, scene_pos, tol: float = 8.0):
        """Hit-test for the nearest drawing within a few pixels of the cursor."""
        mp = self.price_vb.mapSceneToView(scene_pos)
        return self.drawings.find_at_view(mp.x(), mp.y(), self._to_px, tol)

    def _show_context_menu(self, global_pos, ts, price, drawing=None):
        menu = QMenu(self)
        if drawing is not None:
            menu.addAction("Delete drawing", lambda: self.drawings.delete(drawing))
            menu.addSeparator()
        menu.addAction("Add journal note",
                       lambda: self.candle_context.emit(global_pos, ts.timestamp(), price))
        menu.addAction("Add indicator…", self.request_indicator_menu.emit)
        draw_menu = menu.addMenu("Draw")
        for label, tool in [("Horizontal line", "hline"), ("Trend line", "trend"),
                            ("Rectangle", "rect"), ("Fib retracement", "fib")]:
            draw_menu.addAction(label, lambda t=tool: self.drawings.start_tool(t))
        menu.addSeparator()
        if self.drawings.selected is not None:
            menu.addAction("Delete selected drawing",
                           self.drawings.delete_selected)
        menu.addAction("Clear all drawings", self.drawings.clear)
        menu.exec(global_pos.toPoint() if hasattr(global_pos, "toPoint") else global_pos)

    def _index_to_x_dt(self, i):
        if self.df is None or not (0 <= i < len(self.df)):
            return None
        return self.df.index[i]

    # ------------------------------------------------------------------ drawings
    def _save_drawings(self):
        self.db.save_drawings(self.ticker, self.timeframe,
                              self.drawings.serialize())

    def load_drawings(self):
        data = self.db.load_drawings(self.ticker, self.timeframe)
        self.drawings.deserialize(data)

    # ------------------------------------------------------------------ indicators
    def set_indicator(self, name: str, enabled: bool, params: dict | None = None):
        if enabled:
            self._indicator_cfg[name] = params or {}
        else:
            self._indicator_cfg.pop(name, None)
        self.refresh_indicators()

    def _clear_indicator(self, name):
        # items are tracked as (plot, item) so we remove from the right plot
        for plot, item in self._indicator_items.pop(name, []):
            try:
                plot.removeItem(item)
            except Exception:
                pass
        if name == "RSI":
            self._set_subpanel(self.rsi_plot, False)
        if name == "MACD":
            self._set_subpanel(self.macd_plot, False)

    def refresh_indicators(self, only: set | None = None):
        if self.df is None or self.df.empty:
            return
        if only is None:
            # everything currently drawn OR currently wanted, so removed
            # indicators get cleared even though they're no longer in the cfg
            names = set(self._indicator_items.keys()) | set(self._indicator_cfg.keys())
        else:
            names = set(only)
        for name in list(names):
            self._clear_indicator(name)
            if name not in self._indicator_cfg:
                continue
            self._draw_indicator(name, self._indicator_cfg[name])

    def _track(self, name, plot, item):
        self._indicator_items.setdefault(name, []).append((plot, item))
        return item

    def _set_subpanel(self, plot, show, height=150):
        """Show/hide an RSI/MACD sub-panel and reflow the splitter so the main
        chart fills the freed space (Qt auto-distributes when a child hides)."""
        if show:
            was_hidden = plot.isHidden()
            if was_hidden:
                plot.show()
            sizes = self.splitter.sizes()
            idx = self.splitter.indexOf(plot)
            if idx >= 0 and (was_hidden or sizes[idx] < 20):
                sizes[0] = max(150, sizes[0] - height)
                sizes[idx] = height
                self.splitter.setSizes(sizes)
        else:
            plot.hide()

    def _add_curve(self, plot, name, x, y, color, width=1.5, style=Qt.SolidLine):
        pen = pg.mkPen(color, width=width, style=style)
        curve = plot.plot(x, y, pen=pen, name=name)
        self._track(name, plot, curve)
        return curve

    def _draw_indicator(self, name, p):
        df = self.df
        x = np.arange(len(df))
        if name.startswith("SMA"):
            period = p.get("period", 50)
            self._add_curve(self.price_plot, name, x,
                            ind.sma(df, period).values, p.get("color", "#42a5f5"),
                            p.get("width", 1.5))
        elif name.startswith("EMA"):
            period = p.get("period", 20)
            self._add_curve(self.price_plot, name, x,
                            ind.ema(df, period).values, p.get("color", "#ffb74d"),
                            p.get("width", 1.5))
        elif name == "Bollinger":
            up, mid, lo = ind.bollinger(df, p.get("period", 20), p.get("mult", 2.0))
            c = p.get("color", "#b39ddb")
            upper = self._add_curve(self.price_plot, name, x, up.values, c, 1)
            self._add_curve(self.price_plot, name, x, mid.values, c, 1, Qt.DashLine)
            lower = self._add_curve(self.price_plot, name, x, lo.values, c, 1)
            fill = pg.FillBetweenItem(upper, lower,
                                      brush=pg.mkBrush(179, 157, 219, 40))
            self.price_plot.addItem(fill)
            self._track(name, self.price_plot, fill)
        elif name == "VWAP":
            res = ind.vwap(df, with_bands=p.get("bands", True))
            self._add_curve(self.price_plot, name, x, res["vwap"].values,
                            p.get("color", "#ffeb3b"), 1.5)
            if p.get("bands", True):
                for key, st in [("upper1", Qt.DashLine), ("lower1", Qt.DashLine)]:
                    self._add_curve(self.price_plot, name, x, res[key].values,
                                    "#9e9e9e", 0.8, st)
        elif name == "VolumeMA":
            self._add_curve(self.volume_plot, name, x,
                            ind.volume_ma(df, p.get("period", 20)).values,
                            "#ffca28", 1.2)
        elif name == "RSI":
            self._set_subpanel(self.rsi_plot, True)
            r = ind.rsi(df, p.get("period", 14))
            self._add_curve(self.rsi_plot, name, x, r.values, "#ab47bc", 1.3)
            for lvl, col in [(70, "#ef5350"), (30, "#26a69a"), (50, "#555")]:
                line = pg.InfiniteLine(pos=lvl, angle=0,
                                       pen=pg.mkPen(col, style=Qt.DashLine))
                self.rsi_plot.addItem(line)
                self._track(name, self.rsi_plot, line)
        elif name == "MACD":
            self._set_subpanel(self.macd_plot, True)
            macd_line, signal_line, hist = ind.macd(df)
            colors = np.where(hist.values >= 0, self.theme["candle_up"],
                              self.theme["candle_down"])
            bar = pg.BarGraphItem(x=x, height=hist.values, width=0.7,
                                  brushes=[pg.mkColor(c) for c in colors])
            self.macd_plot.addItem(bar)
            self._track(name, self.macd_plot, bar)
            self._add_curve(self.macd_plot, name, x, macd_line.values, "#42a5f5", 1.2)
            self._add_curve(self.macd_plot, name, x, signal_line.values, "#ff7043", 1.2)
        elif name == "ATR":
            a = ind.atr(df, p.get("period", 14))
            txt = pg.TextItem(f"ATR({p.get('period', 14)}): {a.iloc[-1]:.2f}",
                              color="#ffca28", anchor=(1, 0))
            (vx0, vx1), (vy0, vy1) = self.price_vb.viewRange()
            txt.setPos(vx1, vy1)
            self.price_plot.addItem(txt)
            self._track(name, self.price_plot, txt)

    # ------------------------------------------------------------------ overlays
    def set_overlay(self, name: str, enabled: bool):
        self._overlay_cfg = getattr(self, "_overlay_cfg", set())
        if enabled:
            self._overlay_cfg.add(name)
        else:
            self._overlay_cfg.discard(name)
        self.refresh_overlays()

    def _hline(self, price, color, label, style=Qt.DashLine, plot=None):
        plot = plot or self.price_plot
        line = pg.InfiniteLine(
            pos=price, angle=0, pen=pg.mkPen(color, style=style),
            label=label, labelOpts={"position": 0.05, "color": color,
                                     "movable": True})
        plot.addItem(line)
        self._overlay_items.append(line)

    def refresh_overlays(self):
        for it in self._overlay_items:
            self.price_plot.removeItem(it)
        self._overlay_items = []
        cfg = getattr(self, "_overlay_cfg", set())
        if self.df is None or self.df.empty or not cfg:
            return
        df = self.df
        period_map = {"prev_day": "D", "prev_week": "W", "prev_month": "ME"}
        for key, freq in period_map.items():
            if key in cfg:
                lv = ov.prior_period_levels(df, freq)
                if lv:
                    tag = key.split("_")[1][:1].upper()
                    self._hline(lv["vah"], self.theme["vah"], f"p{tag} VAH")
                    self._hline(lv["poc"], self.theme["poc"], f"p{tag} POC")
                    self._hline(lv["val"], self.theme["val"], f"p{tag} VAL")
        if "session_open" in cfg:
            so = ov.session_open(df)
            if so:
                self._hline(so, "#42a5f5", "Open", Qt.SolidLine)
        if "overnight" in cfg:
            onr = ov.overnight_range(df)
            if onr:
                self._hline(onr["high"], "#90a4ae", "ON High")
                self._hline(onr["low"], "#90a4ae", "ON Low")
        if "naked_poc" in cfg:
            for p in ov.naked_pocs(df):
                self._hline(p, "#ff9800", "nPOC", Qt.DotLine)
        if "sessions" in cfg:
            for b in ov.session_boundaries(df):
                line = pg.InfiniteLine(pos=b, angle=90,
                                       pen=pg.mkPen("#37474f", style=Qt.DotLine))
                self.price_plot.addItem(line)
                self._overlay_items.append(line)

    # ------------------------------------------------------------------ profiles
    def set_profile_mode(self, mode):
        self._profile_mode = mode
        self.refresh_profile()

    def set_market_profile(self, enabled: bool):
        self._mp_enabled = enabled
        self.refresh_profile()

    def _profile_source_df(self):
        df = self.df
        if df is None or df.empty:
            return None
        if self._profile_mode == "visible":
            (x0, x1), _ = self.price_vb.viewRange()
            i0 = max(0, int(np.floor(x0))); i1 = min(len(df), int(np.ceil(x1)))
            return df.iloc[i0:i1]
        if self._profile_mode == "sessions":
            groups = list(ov._period_groups(df, "D"))
            if not groups:
                return df
            n = min(3, len(groups))
            return pd.concat([g[1] for g in groups[-n:]])
        return df

    def refresh_profile(self):
        for it in self._profile_items:
            try:
                self.price_plot.removeItem(it)
            except Exception:
                pass
        self._profile_items = []
        if not self._profile_mode and not self._mp_enabled:
            return
        src = self._profile_source_df()
        if src is None or src.empty:
            return
        n = len(self.df)
        if self._profile_mode:
            res = prof.volume_profile(src, bins=40)
            if res is not None:
                self._draw_volume_profile(res, n)
        if self._mp_enabled:
            groups = list(ov._period_groups(self.df, "D"))
            if groups:
                mp = prof.market_profile(groups[-1][1], bins=40)
                if mp is not None:
                    self._draw_market_profile(mp)

    def _draw_volume_profile(self, res: prof.ProfileResult, n: int):
        (x0, x1), _ = self.price_vb.viewRange()
        span = (x1 - x0)
        max_w = span * 0.18
        cmax = res.counts.max() or 1
        right = x1 - 1
        for center, count in zip(res.bin_centers, res.counts):
            w = (count / cmax) * max_w
            if w <= 0:
                continue
            is_poc = abs(center - res.poc_price) < res.bin_size / 2
            color = QColor(self.theme["poc"]) if is_poc else QColor(self.theme["accent"])
            color.setAlpha(160 if is_poc else 90)
            bar = pg.BarGraphItem(x0=[right - w], x1=[right], y0=[center - res.bin_size / 2],
                                  y1=[center + res.bin_size / 2], brush=color, pen=None)
            self.price_plot.addItem(bar)
            self._profile_items.append(bar)
        # VAH/VAL lines + shaded VA
        for price, col, lbl in [(res.vah, self.theme["vah"], "VAH"),
                                (res.val, self.theme["val"], "VAL")]:
            line = pg.InfiniteLine(pos=price, angle=0,
                                   pen=pg.mkPen(col, style=Qt.DashLine),
                                   label=lbl, labelOpts={"color": col})
            self.price_plot.addItem(line)
            self._profile_items.append(line)
        va = pg.LinearRegionItem(values=(res.val, res.vah), orientation="horizontal",
                                 movable=False, brush=pg.mkBrush(41, 98, 255, 25))
        va.setZValue(-10)
        self.price_plot.addItem(va)
        self._profile_items.append(va)

    def _draw_market_profile(self, mp: prof.MarketProfileResult):
        # draw TPO letters left side
        for center, letters in zip(mp.bin_centers, mp.letters):
            if not letters:
                continue
            t = pg.TextItem(letters, color="#80cbc4", anchor=(0, 0.5))
            t.setPos(2, center)
            self.price_plot.addItem(t)
            self._profile_items.append(t)
        for price, col, lbl in [(mp.ib_high, "#ffb74d", "IB High"),
                                (mp.ib_low, "#ffb74d", "IB Low")]:
            line = pg.InfiniteLine(pos=price, angle=0,
                                   pen=pg.mkPen(col, style=Qt.DashLine),
                                   label=lbl, labelOpts={"color": col})
            self.price_plot.addItem(line)
            self._profile_items.append(line)

    # ------------------------------------------------------------------ markers
    def clear_markers(self):
        for it in self._marker_items:
            self.price_plot.removeItem(it)
        self._marker_items = []

    def add_marker(self, ts, price, symbol, color, text=None):
        if self.df is None or self.df.empty:
            return
        # nearest index for timestamp
        idx = self.df.index.get_indexer([pd.Timestamp(ts, unit="s", tz="UTC")],
                                        method="nearest")
        i = int(idx[0]) if idx[0] != -1 else len(self.df) - 1
        sp = pg.ScatterPlotItem([i], [price], symbol=symbol, size=14,
                                brush=pg.mkBrush(color), pen=pg.mkPen("k"))
        self.price_plot.addItem(sp)
        self._marker_items.append(sp)
        if text:
            t = pg.TextItem(text, color=color, anchor=(0.5, 1.2))
            t.setPos(i, price)
            self.price_plot.addItem(t)
            self._marker_items.append(t)

    def clear_order_lines(self):
        for it in self._order_line_items:
            try:
                self.price_plot.removeItem(it)
            except Exception:
                pass
        self._order_line_items = []

    def add_order_line(self, price, label, color):
        line = pg.InfiniteLine(pos=price, angle=0,
                               pen=pg.mkPen(color, style=Qt.DashLine, width=1.5),
                               label=label, labelOpts={"color": color,
                                                       "position": 0.95})
        self.price_plot.addItem(line)
        self._order_line_items.append(line)
        return line
