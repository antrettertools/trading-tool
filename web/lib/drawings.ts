// Drawing tool data model: creation and pixel-space hit-testing. Port of the
// data side of ../chart/drawings.py's BaseDrawing hierarchy (v1 ships the
// core subset: hline, vline, trend, rect, text — see the plan for the
// Fibonacci/pitchfork fast-follow). Canvas rendering lives in
// components/DrawingLayer.tsx, which is where pyqtgraph's job is replaced.
import type { Drawing, DrawingKind } from "./types";

export const CLICK_POINTS: Record<DrawingKind, number> = {
  hline: 1,
  vline: 1,
  trend: 2,
  rect: 2,
  text: 1,
};

export type ToPx = (time: number, price: number) => [number, number] | null;

let counter = 0;
function newId(): string {
  counter += 1;
  return `d${Date.now()}_${counter}`;
}

export function createDrawing(
  kind: DrawingKind,
  points: [number, number][],
  color: string,
  width: number,
  text?: string
): Drawing {
  const base = { id: newId(), color, width };
  switch (kind) {
    case "hline":
      return { ...base, kind, y: points[0][1] };
    case "vline":
      return { ...base, kind, x: points[0][0] };
    case "trend":
      return { ...base, kind, p1: points[0], p2: points[1] };
    case "rect":
      return { ...base, kind, p1: points[0], p2: points[1] };
    case "text":
      return { ...base, kind, x: points[0][0], y: points[0][1], text: text ?? "" };
  }
}

function segDist(px: number, py: number, ax: number, ay: number, bx: number, by: number): number {
  const dx = bx - ax;
  const dy = by - ay;
  if (dx === 0 && dy === 0) return Math.hypot(px - ax, py - ay);
  let t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy);
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

export function hitDistance(d: Drawing, px: number, py: number, toPx: ToPx): number {
  switch (d.kind) {
    case "hline": {
      const p = toPx(0, d.y);
      return p ? Math.abs(py - p[1]) : Infinity;
    }
    case "vline": {
      const p = toPx(d.x, 0);
      return p ? Math.abs(px - p[0]) : Infinity;
    }
    case "trend": {
      const a = toPx(d.p1[0], d.p1[1]);
      const b = toPx(d.p2[0], d.p2[1]);
      if (!a || !b) return Infinity;
      return segDist(px, py, a[0], a[1], b[0], b[1]);
    }
    case "rect": {
      const a = toPx(d.p1[0], d.p1[1]);
      const b = toPx(d.p2[0], d.p2[1]);
      if (!a || !b) return Infinity;
      const [x0, x1] = a[0] < b[0] ? [a[0], b[0]] : [b[0], a[0]];
      const [y0, y1] = a[1] < b[1] ? [a[1], b[1]] : [b[1], a[1]];
      if (px >= x0 && px <= x1 && py >= y0 && py <= y1) return 0;
      const edges: [number, number, number, number][] = [
        [x0, y0, x1, y0],
        [x1, y0, x1, y1],
        [x1, y1, x0, y1],
        [x0, y1, x0, y0],
      ];
      return Math.min(...edges.map((e) => segDist(px, py, ...e)));
    }
    case "text": {
      const p = toPx(d.x, d.y);
      return p ? Math.hypot(px - p[0], py - p[1]) : Infinity;
    }
  }
}
