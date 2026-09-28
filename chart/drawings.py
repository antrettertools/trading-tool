"""Drawing tools and their manager.

Drawings live on the price plot using an index-based x coordinate (matching the
candles). Each tool serializes to a dict so it can be persisted per
ticker/timeframe via the database. Click-to-place tools collect their points
through DrawingManager.handle_click; afterwards endpoints are draggable.
"""
from __future__ import annotations

import pyqtgraph as pg
from PySide6.QtCore import Qt, QObject, Signal

FIB_LEVELS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
FIB_EXT_LEVELS = [0.0, 0.618, 1.0, 1.618, 2.618]

_STYLE = {"solid": Qt.SolidLine, "dashed": Qt.DashLine, "dotted": Qt.DotLine}


def _seg_dist(px, py, ax, ay, bx, by) -> float:
    """Distance from point (px,py) to segment (ax,ay)-(bx,by), all in pixels."""
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


class BaseDrawing:
    kind = "base"

    def __init__(self, plot, color="#ffffff", style="solid", width=1.5):
        self.plot = plot
        self.color = color
        self.style = style
        self.width = width
        self.items: list = []
        self.selected = False

    def pen(self):
        return pg.mkPen(self.color, width=self.width,
                        style=_STYLE.get(self.style, Qt.SolidLine))

    def add(self):
        raise NotImplementedError

    def remove(self):
        for it in self.items:
            try:
                self.plot.removeItem(it)
            except Exception:
                pass
        self.items = []

    def hit_distance(self, px, py, to_px) -> float:
        """Pixel distance from a click (px,py) to this drawing's geometry.
        ``to_px(x, y)`` maps view/data coords to scene pixel coords.
        Subclasses override; default never matches."""
        return float("inf")

    def _segments_distance(self, px, py, segments, to_px) -> float:
        best = float("inf")
        for ax, ay, bx, by in segments:
            pax, pay = to_px(ax, ay)
            pbx, pby = to_px(bx, by)
            best = min(best, _seg_dist(px, py, pax, pay, pbx, pby))
        return best

    def set_selected(self, sel: bool):
        """Highlight (yellow, thicker) while selected; restore on deselect."""
        self.selected = sel
        for it in self.items:
            if hasattr(it, "setPen"):
                if sel:
                    it.setPen(pg.mkPen("#ffeb3b", width=self.width + 1.5,
                                       style=_STYLE.get(self.style, Qt.SolidLine)))
                else:
                    it.setPen(self.pen())
            elif hasattr(it, "setColor"):
                it.setColor("#ffeb3b" if sel else self.color)

    def serialize(self) -> dict:
        d = {"kind": self.kind, "color": self.color,
             "style": self.style, "width": self.width}
        d.update(self._payload())
        return d

    def _payload(self) -> dict:
        return {}


class HLine(BaseDrawing):
    kind = "hline"

    def __init__(self, plot, y, **kw):
        super().__init__(plot, **kw)
        self.y = y

    def add(self):
        line = pg.InfiniteLine(pos=self.y, angle=0, movable=True, pen=self.pen())
        self.plot.addItem(line)
        self.items = [line]

    def _payload(self):
        return {"y": self.items[0].value() if self.items else self.y}

    def hit_distance(self, px, py, to_px):
        y = self.items[0].value() if self.items else self.y
        return abs(py - to_px(0, y)[1])


class VLine(BaseDrawing):
    kind = "vline"

    def __init__(self, plot, x, **kw):
        super().__init__(plot, **kw)
        self.x = x

    def add(self):
        line = pg.InfiniteLine(pos=self.x, angle=90, movable=True, pen=self.pen())
        self.plot.addItem(line)
        self.items = [line]

    def _payload(self):
        return {"x": self.items[0].value() if self.items else self.x}

    def hit_distance(self, px, py, to_px):
        x = self.items[0].value() if self.items else self.x
        return abs(px - to_px(x, 0)[0])


class _TwoPoint(BaseDrawing):
    """Base for tools defined by two draggable handle points."""

    def __init__(self, plot, p1, p2, **kw):
        super().__init__(plot, **kw)
        self.p1 = list(p1)
        self.p2 = list(p2)

    def _payload(self):
        return {"p1": self.p1, "p2": self.p2}

    def _segments(self):
        return [(self.p1[0], self.p1[1], self.p2[0], self.p2[1])]

    def hit_distance(self, px, py, to_px):
        return self._segments_distance(px, py, self._segments(), to_px)


class TrendLine(_TwoPoint):
    kind = "trend"

    def add(self):
        line = pg.LineSegmentROI([self.p1, self.p2], pen=self.pen())
        line.sigRegionChanged.connect(self._sync)
        self.plot.addItem(line)
        self.items = [line]

    def _sync(self):
        h = self.items[0].getSceneHandlePositions()
        pts = [self.items[0].mapSceneToParent(p[1]) for p in h]
        self.p1 = [pts[0].x(), pts[0].y()]
        self.p2 = [pts[1].x(), pts[1].y()]


class Ray(_TwoPoint):
    kind = "ray"

    def add(self):
        # represent as a long segment from p1 through p2
        dx = self.p2[0] - self.p1[0]
        dy = self.p2[1] - self.p1[1]
        far = [self.p1[0] + dx * 1000, self.p1[1] + dy * 1000]
        line = pg.PlotDataItem([self.p1[0], far[0]], [self.p1[1], far[1]],
                               pen=self.pen())
        self.plot.addItem(line)
        self.items = [line]

    def _segments(self):
        dx = self.p2[0] - self.p1[0]
        dy = self.p2[1] - self.p1[1]
        return [(self.p1[0], self.p1[1],
                 self.p1[0] + dx * 1000, self.p1[1] + dy * 1000)]


class ExtendedLine(_TwoPoint):
    kind = "extended"

    def add(self):
        dx = self.p2[0] - self.p1[0]
        dy = self.p2[1] - self.p1[1]
        a = [self.p1[0] - dx * 1000, self.p1[1] - dy * 1000]
        b = [self.p1[0] + dx * 1000, self.p1[1] + dy * 1000]
        line = pg.PlotDataItem([a[0], b[0]], [a[1], b[1]], pen=self.pen())
        self.plot.addItem(line)
        self.items = [line]

    def _segments(self):
        dx = self.p2[0] - self.p1[0]
        dy = self.p2[1] - self.p1[1]
        return [(self.p1[0] - dx * 1000, self.p1[1] - dy * 1000,
                 self.p1[0] + dx * 1000, self.p1[1] + dy * 1000)]


class Rectangle(_TwoPoint):
    kind = "rect"

    def add(self):
        x = min(self.p1[0], self.p2[0]); y = min(self.p1[1], self.p2[1])
        w = abs(self.p2[0] - self.p1[0]); h = abs(self.p2[1] - self.p1[1])
        roi = pg.RectROI([x, y], [w, h], pen=self.pen(),
                         movable=True, resizable=True)
        brush = pg.mkBrush(self.color)
        c = brush.color(); c.setAlpha(40); brush.setColor(c)
        roi.sigRegionChanged.connect(self._sync)
        self.plot.addItem(roi)
        self.items = [roi]

    def _sync(self):
        roi = self.items[0]
        pos = roi.pos(); size = roi.size()
        self.p1 = [pos.x(), pos.y()]
        self.p2 = [pos.x() + size.x(), pos.y() + size.y()]

    def hit_distance(self, px, py, to_px):
        ax, ay = to_px(self.p1[0], self.p1[1])
        bx, by = to_px(self.p2[0], self.p2[1])
        x0, x1 = sorted((ax, bx)); y0, y1 = sorted((ay, by))
        if x0 <= px <= x1 and y0 <= py <= y1:
            return 0.0   # clicking inside the box selects it
        edges = [(x0, y0, x1, y0), (x1, y0, x1, y1),
                 (x1, y1, x0, y1), (x0, y1, x0, y0)]
        return min(_seg_dist(px, py, *e) for e in edges)


class Fib(_TwoPoint):
    kind = "fib"
    levels = FIB_LEVELS
    prefix = "Fib"

    def add(self):
        y1, y2 = self.p1[1], self.p2[1]
        x1, x2 = self.p1[0], self.p2[0]
        diff = y2 - y1
        for lvl in self.levels:
            y = y1 + diff * lvl
            line = pg.PlotDataItem([min(x1, x2), max(x1, x2)], [y, y],
                                   pen=self.pen())
            t = pg.TextItem(f"{lvl*100:.1f}% {y:.2f}", color=self.color,
                            anchor=(0, 0.5))
            t.setPos(max(x1, x2), y)
            self.plot.addItem(line); self.plot.addItem(t)
            self.items += [line, t]

    def _segments(self):
        y1, y2 = self.p1[1], self.p2[1]
        x1, x2 = self.p1[0], self.p2[0]
        diff = y2 - y1
        return [(min(x1, x2), y1 + diff * lvl, max(x1, x2), y1 + diff * lvl)
                for lvl in self.levels]

    def hit_distance(self, px, py, to_px):
        return self._segments_distance(px, py, self._segments(), to_px)


class FibExt(Fib):
    kind = "fibext"
    levels = FIB_EXT_LEVELS
    prefix = "FibExt"


class Pitchfork(BaseDrawing):
    kind = "pitchfork"

    def __init__(self, plot, p1, p2, p3, **kw):
        super().__init__(plot, **kw)
        self.p1, self.p2, self.p3 = list(p1), list(p2), list(p3)

    def add(self):
        # median line from p1 through midpoint of p2,p3; parallels through p2,p3
        mid = [(self.p2[0] + self.p3[0]) / 2, (self.p2[1] + self.p3[1]) / 2]
        dx, dy = mid[0] - self.p1[0], mid[1] - self.p1[1]
        ext = 3.0
        def seg(start):
            return ([start[0], start[0] + dx * ext], [start[1], start[1] + dy * ext])
        for start in (self.p1, self.p2, self.p3):
            xs, ys = seg(start)
            line = pg.PlotDataItem(xs, ys, pen=self.pen())
            self.plot.addItem(line)
            self.items.append(line)

    def _payload(self):
        return {"p1": self.p1, "p2": self.p2, "p3": self.p3}

    def hit_distance(self, px, py, to_px):
        mid = [(self.p2[0] + self.p3[0]) / 2, (self.p2[1] + self.p3[1]) / 2]
        dx, dy = mid[0] - self.p1[0], mid[1] - self.p1[1]
        ext = 3.0
        segs = [(s[0], s[1], s[0] + dx * ext, s[1] + dy * ext)
                for s in (self.p1, self.p2, self.p3)]
        return self._segments_distance(px, py, segs, to_px)


class TextLabel(BaseDrawing):
    kind = "text"

    def __init__(self, plot, x, y, text="", **kw):
        super().__init__(plot, **kw)
        self.x, self.y, self.text = x, y, text

    def add(self):
        t = pg.TextItem(self.text or "text", color=self.color, anchor=(0, 0.5))
        t.setPos(self.x, self.y)
        self.plot.addItem(t)
        self.items = [t]

    def _payload(self):
        return {"x": self.x, "y": self.y, "text": self.text}

    def hit_distance(self, px, py, to_px):
        ax, ay = to_px(self.x, self.y)
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5


_REGISTRY = {c.kind: c for c in [HLine, VLine, TrendLine, Ray, ExtendedLine,
                                 Rectangle, Fib, FibExt, Pitchfork, TextLabel]}
# tools defined by N clicks
_CLICK_POINTS = {"hline": 1, "vline": 1, "trend": 2, "ray": 2, "extended": 2,
                 "rect": 2, "fib": 2, "fibext": 2, "pitchfork": 3, "text": 1}


class DrawingManager(QObject):
    changed = Signal()

    def __init__(self, plot, theme, index_to_dt=None):
        super().__init__()
        self.plot = plot
        self.theme = theme
        self.index_to_dt = index_to_dt
        self.drawings: list[BaseDrawing] = []
        self.selected: BaseDrawing | None = None
        self.active_tool: str | None = None
        self._pending_points: list = []
        self.color = "#d1d4dc"
        self.style = "solid"
        self.ticker = None
        self.timeframe = None
        self.text_prompt = None  # callable returning text for TextLabel

    def set_context(self, ticker, timeframe):
        self.ticker, self.timeframe = ticker, timeframe

    # ------------------------------------------------------------- selection
    def find_at_view(self, vx, vy, to_px, tol: float = 8.0) -> "BaseDrawing | None":
        """Return the nearest drawing within ``tol`` pixels of a click.
        ``vx, vy`` are view/data coords; ``to_px(x, y)`` maps to scene pixels."""
        px, py = to_px(vx, vy)
        best, best_d = None, tol
        for d in self.drawings:
            try:
                dist = d.hit_distance(px, py, to_px)
            except Exception:
                continue
            if dist <= best_d:
                best, best_d = d, dist
        return best

    def select(self, drawing: "BaseDrawing | None"):
        if self.selected is drawing:
            return
        if self.selected is not None:
            self.selected.set_selected(False)
        self.selected = drawing
        if drawing is not None:
            drawing.set_selected(True)

    def delete(self, drawing: "BaseDrawing"):
        drawing.remove()
        if drawing in self.drawings:
            self.drawings.remove(drawing)
        if self.selected is drawing:
            self.selected = None
        self.changed.emit()

    def delete_selected(self):
        if self.selected is not None:
            self.delete(self.selected)

    def start_tool(self, kind: str):
        self.active_tool = kind
        self._pending_points = []

    def cancel_tool(self):
        self.active_tool = None
        self._pending_points = []

    def handle_click(self, x, y):
        if not self.active_tool:
            return
        self._pending_points.append([x, y])
        needed = _CLICK_POINTS.get(self.active_tool, 2)
        if len(self._pending_points) >= needed:
            self._finish_tool()

    def _finish_tool(self):
        kind = self.active_tool
        pts = self._pending_points
        kw = {"color": self.color, "style": self.style}
        try:
            if kind == "hline":
                d = HLine(self.plot, pts[0][1], **kw)
            elif kind == "vline":
                d = VLine(self.plot, pts[0][0], **kw)
            elif kind == "text":
                txt = self.text_prompt() if self.text_prompt else "text"
                d = TextLabel(self.plot, pts[0][0], pts[0][1], text=txt or "", **kw)
            elif kind == "pitchfork":
                d = Pitchfork(self.plot, pts[0], pts[1], pts[2], **kw)
            else:
                cls = _REGISTRY[kind]
                d = cls(self.plot, pts[0], pts[1], **kw)
            d.add()
            self.drawings.append(d)
            self.changed.emit()
        finally:
            self.cancel_tool()

    def clear(self):
        for d in self.drawings:
            d.remove()
        self.drawings = []
        self.selected = None
        self.changed.emit()

    def serialize(self) -> list[dict]:
        return [d.serialize() for d in self.drawings]

    def deserialize(self, data: list[dict]):
        for d in self.drawings:
            d.remove()
        self.drawings = []
        self.selected = None
        for item in data:
            kind = item.get("kind")
            cls = _REGISTRY.get(kind)
            if not cls:
                continue
            kw = {"color": item.get("color", "#d1d4dc"),
                  "style": item.get("style", "solid"),
                  "width": item.get("width", 1.5)}
            try:
                if kind == "hline":
                    d = cls(self.plot, item["y"], **kw)
                elif kind == "vline":
                    d = cls(self.plot, item["x"], **kw)
                elif kind == "text":
                    d = cls(self.plot, item["x"], item["y"],
                            text=item.get("text", ""), **kw)
                elif kind == "pitchfork":
                    d = cls(self.plot, item["p1"], item["p2"], item["p3"], **kw)
                else:
                    d = cls(self.plot, item["p1"], item["p2"], **kw)
                d.add()
                self.drawings.append(d)
            except (KeyError, Exception):
                continue
