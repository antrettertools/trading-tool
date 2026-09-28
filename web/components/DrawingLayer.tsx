"use client";

// Interactive canvas overlay for chart drawing tools: click-to-place,
// select, drag, delete. Port of the interaction model in
// ../chart/drawings.py's DrawingManager, reworked against lightweight-charts'
// coordinate APIs instead of pyqtgraph's scene.
import { useCallback, useEffect, useRef } from "react";
import type { IChartApi, ISeriesApi, Time } from "lightweight-charts";
import type { Drawing, DrawingKind, JournalNote } from "@/lib/types";
import { CLICK_POINTS, createDrawing, hitDistance, type ToPx } from "@/lib/drawings";
import { theme } from "@/lib/theme";

interface Props {
  chart: IChartApi | null;
  series: ISeriesApi<"Candlestick"> | null;
  drawings: Drawing[];
  onDrawingsChange: (d: Drawing[]) => void;
  activeTool: DrawingKind | null;
  onToolDone: () => void;
  drawColor: string;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onContextMenuAt: (time: number, price: number) => void;
  textPrompt: () => string | null;
  journalNotes: JournalNote[];
  onJournalNoteClick: (note: JournalNote) => void;
}

const HIT_TOLERANCE = 8;
const FLAG_RADIUS = 6;

export default function DrawingLayer({
  chart, series, drawings, onDrawingsChange, activeTool, onToolDone,
  drawColor, selectedId, onSelect, onContextMenuAt, textPrompt,
  journalNotes, onJournalNoteClick,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pendingRef = useRef<[number, number][]>([]);
  const dragRef = useRef<{ id: string; point: "p1" | "p2" | "single" } | null>(null);
  const drawingsRef = useRef(drawings);
  const notesRef = useRef(journalNotes);
  useEffect(() => {
    drawingsRef.current = drawings;
    notesRef.current = journalNotes;
  }, [drawings, journalNotes]);

  const toPx = useCallback<ToPx>(
    (time, price) => {
      if (!chart || !series) return null;
      const x = chart.timeScale().timeToCoordinate(time as Time);
      const y = series.priceToCoordinate(price);
      if (x == null || y == null) return null;
      return [x, y];
    },
    [chart, series]
  );

  const toData = useCallback(
    (px: number, py: number): [number, number] | null => {
      if (!chart || !series) return null;
      const t = chart.timeScale().coordinateToTime(px);
      const p = series.coordinateToPrice(py);
      if (t == null || p == null) return null;
      return [t as unknown as number, p];
    },
    [chart, series]
  );

  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !chart) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    if (canvas.width !== rect.width * dpr || canvas.height !== rect.height * dpr) {
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, rect.width, rect.height);

    for (const d of drawingsRef.current) {
      const isSelected = d.id === selectedId;
      ctx.strokeStyle = isSelected ? "#ffeb3b" : d.color;
      ctx.fillStyle = isSelected ? "#ffeb3b" : d.color;
      ctx.lineWidth = isSelected ? d.width + 1.5 : d.width;
      ctx.setLineDash([]);

      if (d.kind === "hline") {
        const p = toPx(0, d.y);
        if (!p) continue;
        ctx.beginPath();
        ctx.moveTo(0, p[1]);
        ctx.lineTo(rect.width, p[1]);
        ctx.stroke();
      } else if (d.kind === "vline") {
        const p = toPx(d.x, 0);
        if (!p) continue;
        ctx.beginPath();
        ctx.moveTo(p[0], 0);
        ctx.lineTo(p[0], rect.height);
        ctx.stroke();
      } else if (d.kind === "trend") {
        const a = toPx(d.p1[0], d.p1[1]);
        const b = toPx(d.p2[0], d.p2[1]);
        if (!a || !b) continue;
        ctx.beginPath();
        ctx.moveTo(a[0], a[1]);
        ctx.lineTo(b[0], b[1]);
        ctx.stroke();
        if (isSelected) {
          [a, b].forEach((p) => {
            ctx.beginPath();
            ctx.arc(p[0], p[1], 4, 0, Math.PI * 2);
            ctx.fill();
          });
        }
      } else if (d.kind === "rect") {
        const a = toPx(d.p1[0], d.p1[1]);
        const b = toPx(d.p2[0], d.p2[1]);
        if (!a || !b) continue;
        const x = Math.min(a[0], b[0]);
        const y = Math.min(a[1], b[1]);
        const w = Math.abs(b[0] - a[0]);
        const h = Math.abs(b[1] - a[1]);
        ctx.globalAlpha = 0.15;
        ctx.fillRect(x, y, w, h);
        ctx.globalAlpha = 1;
        ctx.strokeRect(x, y, w, h);
      } else if (d.kind === "text") {
        const p = toPx(d.x, d.y);
        if (!p) continue;
        ctx.font = "12px -apple-system, sans-serif";
        ctx.textBaseline = "middle";
        ctx.fillText(d.text || "text", p[0] + 4, p[1]);
      }
    }

    ctx.setLineDash([]);
    for (const note of notesRef.current) {
      if (note.price == null) continue;
      const p = toPx(note.ts, note.price);
      if (!p) continue;
      ctx.beginPath();
      ctx.arc(p[0], p[1], FLAG_RADIUS, 0, Math.PI * 2);
      ctx.fillStyle = theme.journalFlag;
      ctx.fill();
      ctx.strokeStyle = "#000";
      ctx.lineWidth = 1;
      ctx.stroke();
    }
  }, [chart, selectedId, toPx]);

  useEffect(() => {
    redraw();
  }, [redraw, drawings, journalNotes]);

  useEffect(() => {
    if (!chart) return;
    const handler = () => redraw();
    chart.timeScale().subscribeVisibleLogicalRangeChange(handler);
    window.addEventListener("resize", handler);
    const ro = new ResizeObserver(handler);
    if (canvasRef.current) ro.observe(canvasRef.current);
    return () => {
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(handler);
      window.removeEventListener("resize", handler);
      ro.disconnect();
    };
  }, [chart, redraw]);

  const finishTool = useCallback(
    (kind: DrawingKind) => {
      const pts = pendingRef.current;
      let text: string | undefined;
      if (kind === "text") {
        text = textPrompt() ?? "";
        if (!text) {
          pendingRef.current = [];
          onToolDone();
          return;
        }
      }
      const d = createDrawing(kind, pts, drawColor, 1.5, text);
      onDrawingsChange([...drawingsRef.current, d]);
      pendingRef.current = [];
      onToolDone();
    },
    [drawColor, onDrawingsChange, onToolDone, textPrompt]
  );

  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const rect = canvasRef.current!.getBoundingClientRect();
      const px = e.clientX - rect.left;
      const py = e.clientY - rect.top;

      if (activeTool) {
        const data = toData(px, py);
        if (!data) return;
        pendingRef.current.push(data);
        if (pendingRef.current.length >= CLICK_POINTS[activeTool]) finishTool(activeTool);
        return;
      }

      let best: Drawing | null = null;
      let bestDist = HIT_TOLERANCE;
      for (const d of drawingsRef.current) {
        const dist = hitDistance(d, px, py, toPx);
        if (dist <= bestDist) {
          best = d;
          bestDist = dist;
        }
      }
      if (best) {
        onSelect(best.id);
        return;
      }
      onSelect(null);
      for (const note of notesRef.current) {
        if (note.price == null) continue;
        const p = toPx(note.ts, note.price);
        if (p && Math.hypot(px - p[0], py - p[1]) <= FLAG_RADIUS + 3) {
          onJournalNoteClick(note);
          break;
        }
      }
    },
    [activeTool, finishTool, onJournalNoteClick, onSelect, toData, toPx]
  );

  const handleContextMenu = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      e.preventDefault();
      const rect = canvasRef.current!.getBoundingClientRect();
      const data = toData(e.clientX - rect.left, e.clientY - rect.top);
      if (data) onContextMenuAt(data[0], data[1]);
    },
    [onContextMenuAt, toData]
  );

  const handleMouseDown = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (activeTool || !selectedId) return;
      const d = drawingsRef.current.find((x) => x.id === selectedId);
      if (!d) return;
      const rect = canvasRef.current!.getBoundingClientRect();
      const px = e.clientX - rect.left;
      const py = e.clientY - rect.top;
      if (d.kind === "trend" || d.kind === "rect") {
        const a = toPx(d.p1[0], d.p1[1]);
        const b = toPx(d.p2[0], d.p2[1]);
        if (a && Math.hypot(px - a[0], py - a[1]) < 10) dragRef.current = { id: d.id, point: "p1" };
        else if (b && Math.hypot(px - b[0], py - b[1]) < 10) dragRef.current = { id: d.id, point: "p2" };
      } else if (hitDistance(d, px, py, toPx) <= HIT_TOLERANCE) {
        dragRef.current = { id: d.id, point: "single" };
      }
    },
    [activeTool, selectedId, toPx]
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const drag = dragRef.current;
      if (!drag) return;
      const rect = canvasRef.current!.getBoundingClientRect();
      const data = toData(e.clientX - rect.left, e.clientY - rect.top);
      if (!data) return;
      const updated = drawingsRef.current.map((d) => {
        if (d.id !== drag.id) return d;
        if (d.kind === "hline") return { ...d, y: data[1] };
        if (d.kind === "vline") return { ...d, x: data[0] };
        if (d.kind === "text") return { ...d, x: data[0], y: data[1] };
        if (d.kind === "trend" || d.kind === "rect") {
          return drag.point === "p1" ? { ...d, p1: data } : { ...d, p2: data };
        }
        return d;
      });
      onDrawingsChange(updated);
    },
    [onDrawingsChange, toData]
  );

  const handleMouseUp = useCallback(() => {
    dragRef.current = null;
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: "absolute",
        inset: 0,
        width: "100%",
        height: "100%",
        cursor: activeTool ? "crosshair" : "default",
      }}
      onClick={handleClick}
      onContextMenu={handleContextMenu}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
    />
  );
}

export const drawColorDefault = theme.text;
