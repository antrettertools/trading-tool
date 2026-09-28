"use client";

// Candlestick + volume chart with indicator/overlay/profile rendering and the
// drawing-tool overlay. Built on lightweight-charts (TradingView's own
// library) as the closest available match to ../chart/engine.py's PyQtGraph
// rendering. See lib/{indicators,profiles,overlays}.ts for the ported math.
import { useCallback, useEffect, useRef, useState } from "react";
import {
  createChart, CandlestickSeries, HistogramSeries, LineSeries,
  ColorType, LineStyle, createSeriesMarkers,
  type IChartApi, type ISeriesApi, type IPriceLine, type Time, type SeriesMarker,
  type ISeriesMarkersPluginApi,
} from "lightweight-charts";
import type {
  Candle, Drawing, DrawingKind, IndicatorConfig, JournalNote, OverlayConfig, ProfileMode,
} from "@/lib/types";
import * as ind from "@/lib/indicators";
import { volumeProfile, marketProfile } from "@/lib/profiles";
import { priorPeriodLevels, sessionOpen, overnightRange, nakedPocs, sessionBoundaries } from "@/lib/overlays";
import { theme } from "@/lib/theme";
import DrawingLayer from "./DrawingLayer";

export interface FillMarker {
  time: number;
  price: number;
  side: "buy" | "sell";
  label: string;
}

export interface OrderLine {
  key: string;
  price: number;
  label: string;
  color: string;
}

interface Props {
  candles: Candle[];
  indicators: IndicatorConfig;
  overlays: OverlayConfig;
  profileMode: ProfileMode;
  marketProfileEnabled: boolean;
  drawings: Drawing[];
  onDrawingsChange: (d: Drawing[]) => void;
  activeTool: DrawingKind | null;
  onToolDone: () => void;
  drawColor: string;
  selectedDrawingId: string | null;
  onSelectDrawing: (id: string | null) => void;
  fillMarkers: FillMarker[];
  journalNotes: JournalNote[];
  onJournalRequest: (time: number, price: number) => void;
  onJournalNoteClick: (note: JournalNote) => void;
  orderLines: OrderLine[];
}

function dayGroups(candles: Candle[]): Candle[][] {
  const map = new Map<number, Candle[]>();
  const order: number[] = [];
  for (const c of candles) {
    const key = Math.floor(c.time / 86400);
    if (!map.has(key)) {
      map.set(key, []);
      order.push(key);
    }
    map.get(key)!.push(c);
  }
  order.sort((a, b) => a - b);
  return order.map((k) => map.get(k)!);
}

function nearestTime(candles: Candle[], ts: number): number | null {
  if (!candles.length) return null;
  let best = candles[0].time;
  let bestDiff = Math.abs(candles[0].time - ts);
  for (const c of candles) {
    const diff = Math.abs(c.time - ts);
    if (diff < bestDiff) {
      bestDiff = diff;
      best = c.time;
    }
  }
  return best;
}

function toLineData(candles: Candle[], values: number[]) {
  const out: { time: Time; value: number }[] = [];
  for (let i = 0; i < candles.length; i++) {
    if (!Number.isNaN(values[i]) && Number.isFinite(values[i])) {
      out.push({ time: candles[i].time as Time, value: values[i] });
    }
  }
  return out;
}

export default function Chart({
  candles, indicators, overlays, profileMode, marketProfileEnabled,
  drawings, onDrawingsChange, activeTool, onToolDone, drawColor,
  selectedDrawingId, onSelectDrawing, fillMarkers, journalNotes,
  onJournalRequest, onJournalNoteClick, orderLines,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const profileCanvasRef = useRef<HTMLCanvasElement>(null);
  const [chart, setChart] = useState<IChartApi | null>(null);
  const [candleSeries, setCandleSeries] = useState<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const rsiSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const macdLineRef = useRef<ISeriesApi<"Line"> | null>(null);
  const macdSignalRef = useRef<ISeriesApi<"Line"> | null>(null);
  const macdHistRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const dynamicSeriesRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const priceLinesRef = useRef<Map<string, IPriceLine>>(new Map());
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);

  // ---- chart + fixed series (created once) ------------------------------
  useEffect(() => {
    if (!containerRef.current) return;
    const c = createChart(containerRef.current, {
      layout: { background: { type: ColorType.Solid, color: theme.background }, textColor: theme.text },
      grid: { vertLines: { color: theme.grid }, horzLines: { color: theme.grid } },
      rightPriceScale: { borderColor: theme.border },
      timeScale: { borderColor: theme.border, timeVisible: true, secondsVisible: false },
      autoSize: true,
    });
    const cs = c.addSeries(CandlestickSeries, {
      upColor: theme.candleUp, downColor: theme.candleDown, borderVisible: false,
      wickUpColor: theme.candleUp, wickDownColor: theme.candleDown,
    }, 0);
    const vs = c.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "vol" }, 1);
    vs.priceScale().applyOptions({ scaleMargins: { top: 0.1, bottom: 0 } });
    c.panes()[1]?.setStretchFactor(0.18);

    const rsiSeries = c.addSeries(LineSeries, { color: "#ab47bc", lineWidth: 1, priceLineVisible: false, lastValueVisible: false }, 2);
    c.panes()[2]?.setStretchFactor(0.0001);
    const macdLine = c.addSeries(LineSeries, { color: "#42a5f5", lineWidth: 1, priceLineVisible: false, lastValueVisible: false }, 3);
    const macdSignal = c.addSeries(LineSeries, { color: "#ffb74d", lineWidth: 1, priceLineVisible: false, lastValueVisible: false }, 3);
    const macdHist = c.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false }, 3);
    c.panes()[3]?.setStretchFactor(0.0001);

    volumeSeriesRef.current = vs;
    rsiSeriesRef.current = rsiSeries;
    macdLineRef.current = macdLine;
    macdSignalRef.current = macdSignal;
    macdHistRef.current = macdHist;
    markersRef.current = createSeriesMarkers(cs, []);

    setChart(c);
    setCandleSeries(cs);

    const dynamicSeries = dynamicSeriesRef.current;
    const priceLines = priceLinesRef.current;
    return () => {
      c.remove();
      setChart(null);
      setCandleSeries(null);
      dynamicSeries.clear();
      priceLines.clear();
    };
  }, []);

  // ---- candle + volume data ----------------------------------------------
  useEffect(() => {
    if (!candleSeries || !volumeSeriesRef.current) return;
    candleSeries.setData(candles.map((c) => ({ time: c.time as Time, open: c.open, high: c.high, low: c.low, close: c.close })));
    volumeSeriesRef.current.setData(
      candles.map((c) => ({
        time: c.time as Time,
        value: c.volume,
        color: c.close >= c.open ? theme.candleUp : theme.candleDown,
      }))
    );
  }, [candleSeries, candles]);

  // ---- indicators ----------------------------------------------------------
  useEffect(() => {
    if (!chart || !candleSeries) return;
    const wanted = new Set<string>();

    const upsertLine = (key: string, pane: number, options: Parameters<ISeriesApi<"Line">["applyOptions"]>[0], data: { time: Time; value: number }[]) => {
      wanted.add(key);
      let s = dynamicSeriesRef.current.get(key);
      if (!s) {
        s = chart.addSeries(LineSeries, { priceLineVisible: false, lastValueVisible: false, ...options }, pane);
        dynamicSeriesRef.current.set(key, s);
      } else {
        s.applyOptions(options);
      }
      s.setData(data);
    };

    for (const ma of indicators.mas) {
      if (!ma.enabled) continue;
      const values = ma.kind === "EMA" ? ind.ema(candles, ma.period) : ind.sma(candles, ma.period);
      const width = Math.min(4, Math.max(1, Math.round(ma.width))) as 1 | 2 | 3 | 4;
      upsertLine(`ma:${ma.id}`, 0, { color: ma.color, lineWidth: width }, toLineData(candles, values));
    }

    if (indicators.bollinger.enabled) {
      const { upper, mid, lower } = ind.bollinger(candles, indicators.bollinger.period, indicators.bollinger.mult);
      upsertLine("bb:upper", 0, { color: "#787b86", lineWidth: 1 }, toLineData(candles, upper));
      upsertLine("bb:mid", 0, { color: "#787b86", lineWidth: 1, lineStyle: LineStyle.Dotted }, toLineData(candles, mid));
      upsertLine("bb:lower", 0, { color: "#787b86", lineWidth: 1 }, toLineData(candles, lower));
    }

    if (indicators.vwap.enabled) {
      const v = ind.vwap(candles, indicators.vwap.bands);
      upsertLine("vwap:mid", 0, { color: theme.accent, lineWidth: 1 }, toLineData(candles, v.vwap));
      if (indicators.vwap.bands) {
        upsertLine("vwap:u1", 0, { color: theme.accent, lineWidth: 1, lineStyle: LineStyle.Dashed }, toLineData(candles, v.upper1));
        upsertLine("vwap:l1", 0, { color: theme.accent, lineWidth: 1, lineStyle: LineStyle.Dashed }, toLineData(candles, v.lower1));
        upsertLine("vwap:u2", 0, { color: theme.accent, lineWidth: 1, lineStyle: LineStyle.Dotted }, toLineData(candles, v.upper2));
        upsertLine("vwap:l2", 0, { color: theme.accent, lineWidth: 1, lineStyle: LineStyle.Dotted }, toLineData(candles, v.lower2));
      }
    }

    if (indicators.volumeMa.enabled) {
      upsertLine("volma", 1, { color: "#ffb74d", lineWidth: 1, priceScaleId: "vol" }, toLineData(candles, ind.volumeMa(candles, 20)));
    }

    for (const [key, s] of dynamicSeriesRef.current) {
      if (!wanted.has(key)) {
        chart.removeSeries(s);
        dynamicSeriesRef.current.delete(key);
      }
    }

    // RSI / MACD live in fixed panes (created once) — just toggle their
    // stretch factor and refresh data so pane indices never shift.
    const rsiPane = chart.panes()[2];
    if (indicators.rsi.enabled) {
      rsiPane?.setStretchFactor(0.22);
      rsiSeriesRef.current?.setData(toLineData(candles, ind.rsi(candles, indicators.rsi.period)));
    } else {
      rsiPane?.setStretchFactor(0.0001);
      rsiSeriesRef.current?.setData([]);
    }

    const macdPane = chart.panes()[3];
    if (indicators.macd.enabled) {
      macdPane?.setStretchFactor(0.22);
      const { macdLine, signalLine, hist } = ind.macd(candles);
      macdLineRef.current?.setData(toLineData(candles, macdLine));
      macdSignalRef.current?.setData(toLineData(candles, signalLine));
      macdHistRef.current?.setData(
        candles.map((c, i) => ({ time: c.time as Time, value: hist[i] || 0, color: hist[i] >= 0 ? theme.candleUp : theme.candleDown }))
          .filter((_, i) => !Number.isNaN(hist[i]))
      );
    } else {
      macdPane?.setStretchFactor(0.0001);
      macdLineRef.current?.setData([]);
      macdSignalRef.current?.setData([]);
      macdHistRef.current?.setData([]);
    }
  }, [chart, candleSeries, candles, indicators]);

  // ---- AMT overlays (horizontal price lines) ------------------------------
  useEffect(() => {
    if (!candleSeries) return;
    const wanted = new Map<string, { price: number; color: string; title: string; dashed?: boolean }>();

    const addLevels = (prefix: string, levels: { vah: number; val: number; poc: number } | null, label: string) => {
      if (!levels) return;
      wanted.set(`${prefix}:vah`, { price: levels.vah, color: theme.vah, title: `${label} VAH`, dashed: true });
      wanted.set(`${prefix}:val`, { price: levels.val, color: theme.val, title: `${label} VAL`, dashed: true });
      wanted.set(`${prefix}:poc`, { price: levels.poc, color: theme.poc, title: `${label} POC`, dashed: true });
    };

    if (overlays.prevDay) addLevels("prevDay", priorPeriodLevels(candles, "day"), "D");
    if (overlays.prevWeek) addLevels("prevWeek", priorPeriodLevels(candles, "week"), "W");
    if (overlays.prevMonth) addLevels("prevMonth", priorPeriodLevels(candles, "month"), "M");

    if (overlays.sessionOpen) {
      const o = sessionOpen(candles);
      if (o != null) wanted.set("sessionOpen", { price: o, color: theme.text, title: "Open" });
    }
    if (overlays.overnight) {
      const r = overnightRange(candles);
      if (r) {
        wanted.set("onHigh", { price: r.high, color: theme.textMuted, title: "ON High", dashed: true });
        wanted.set("onLow", { price: r.low, color: theme.textMuted, title: "ON Low", dashed: true });
      }
    }
    if (overlays.nakedPoc) {
      nakedPocs(candles).forEach((poc, i) => {
        wanted.set(`naked:${i}`, { price: poc, color: theme.poc, title: "Naked POC", dashed: true });
      });
    }

    for (const [key, opts] of wanted) {
      let line = priceLinesRef.current.get(key);
      const lineOptions = {
        price: opts.price, color: opts.color, lineWidth: 1 as const,
        lineStyle: opts.dashed ? LineStyle.Dashed : LineStyle.Solid,
        axisLabelVisible: true, title: opts.title,
      };
      if (!line) {
        line = candleSeries.createPriceLine(lineOptions);
        priceLinesRef.current.set(key, line);
      } else {
        line.applyOptions(lineOptions);
      }
    }
    for (const [key, line] of priceLinesRef.current) {
      if (key.startsWith("order:")) continue;
      if (!wanted.has(key)) {
        candleSeries.removePriceLine(line);
        priceLinesRef.current.delete(key);
      }
    }
  }, [candleSeries, candles, overlays]);

  // ---- order lines (open orders) -------------------------------------------
  useEffect(() => {
    if (!candleSeries) return;
    const wantedKeys = new Set(orderLines.map((o) => `order:${o.key}`));
    for (const ol of orderLines) {
      const key = `order:${ol.key}`;
      const opts = { price: ol.price, color: ol.color, lineWidth: 1 as const, lineStyle: LineStyle.Dashed, title: ol.label, axisLabelVisible: true };
      let line = priceLinesRef.current.get(key);
      if (!line) {
        line = candleSeries.createPriceLine(opts);
        priceLinesRef.current.set(key, line);
      } else {
        line.applyOptions(opts);
      }
    }
    for (const [key, line] of priceLinesRef.current) {
      if (key.startsWith("order:") && !wantedKeys.has(key)) {
        candleSeries.removePriceLine(line);
        priceLinesRef.current.delete(key);
      }
    }
  }, [candleSeries, orderLines]);

  // ---- fill markers ----------------------------------------------------------
  useEffect(() => {
    if (!markersRef.current) return;
    const markers: SeriesMarker<Time>[] = fillMarkers
      .map((m) => {
        const t = nearestTime(candles, m.time);
        if (t == null) return null;
        return {
          time: t as Time,
          position: m.side === "buy" ? "belowBar" : "aboveBar",
          color: m.side === "buy" ? theme.candleUp : theme.candleDown,
          shape: m.side === "buy" ? "arrowUp" : "arrowDown",
          text: m.label,
        } as SeriesMarker<Time>;
      })
      .filter((m): m is SeriesMarker<Time> => m != null)
      .sort((a, b) => (a.time as number) - (b.time as number));
    markersRef.current.setMarkers(markers);
  }, [candles, fillMarkers]);

  // ---- profile (volume profile / market profile TPO) canvas overlay ------
  const redrawProfile = useCallback(() => {
    const canvas = profileCanvasRef.current;
    if (!canvas || !chart || !candleSeries) return;
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

    const drawProfile = (
      prof: { binCenters: number[]; counts: number[]; binSize: number; poc: number; vah: number; val: number } | null,
      color: string,
      side: "right" | "left",
      maxWidthFrac: number
    ) => {
      if (!prof) return;
      const maxCount = Math.max(...prof.counts, 1e-9);
      const maxWidth = rect.width * maxWidthFrac;
      prof.binCenters.forEach((center, i) => {
        const yTop = candleSeries.priceToCoordinate(center + prof.binSize / 2);
        const yBot = candleSeries.priceToCoordinate(center - prof.binSize / 2);
        if (yTop == null || yBot == null) return;
        const w = (prof.counts[i] / maxCount) * maxWidth;
        const inValueArea = center <= prof.vah && center >= prof.val;
        ctx.fillStyle = color;
        ctx.globalAlpha = inValueArea ? 0.35 : 0.18;
        const h = Math.max(1, Math.abs(yBot - yTop) - 1);
        const y = Math.min(yTop, yBot);
        if (side === "right") ctx.fillRect(rect.width - w, y, w, h);
        else ctx.fillRect(0, y, w, h);
      });
      ctx.globalAlpha = 1;
      const pocY = candleSeries.priceToCoordinate(prof.poc);
      if (pocY != null) {
        ctx.strokeStyle = theme.poc;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(side === "right" ? rect.width - maxWidth : 0, pocY);
        ctx.lineTo(side === "right" ? rect.width : maxWidth, pocY);
        ctx.stroke();
      }
    };

    if (profileMode !== "off") {
      let source = candles;
      if (profileMode === "visible") {
        const range = chart.timeScale().getVisibleRange();
        if (range) {
          source = candles.filter((c) => c.time >= (range.from as number) && c.time <= (range.to as number));
        }
      } else {
        const groups = dayGroups(candles).slice(-3);
        source = groups.flat();
      }
      drawProfile(volumeProfile(source, 40), theme.candleUp, "right", 0.12);
    }

    if (marketProfileEnabled) {
      const groups = dayGroups(candles);
      const today = groups[groups.length - 1] ?? [];
      const mp = marketProfile(today, 40);
      drawProfile(mp, "#42a5f5", "left", 0.1);
    }

    if (overlays.sessions) {
      ctx.strokeStyle = theme.border;
      ctx.setLineDash([4, 4]);
      for (const idx of sessionBoundaries(candles)) {
        const c = candles[idx];
        const x = chart.timeScale().timeToCoordinate(c.time as Time);
        if (x == null) continue;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, rect.height);
        ctx.stroke();
      }
      ctx.setLineDash([]);
    }
  }, [chart, candleSeries, candles, profileMode, marketProfileEnabled, overlays.sessions]);

  useEffect(() => {
    redrawProfile();
  }, [redrawProfile]);

  useEffect(() => {
    if (!chart) return;
    const handler = () => redrawProfile();
    chart.timeScale().subscribeVisibleLogicalRangeChange(handler);
    window.addEventListener("resize", handler);
    return () => {
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(handler);
      window.removeEventListener("resize", handler);
    };
  }, [chart, redrawProfile]);

  const textPrompt = useCallback(() => window.prompt("Enter text:"), []);

  return (
    <div ref={containerRef} style={{ position: "relative", width: "100%", height: "100%" }}>
      <canvas ref={profileCanvasRef} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }} />
      <DrawingLayer
        chart={chart}
        series={candleSeries}
        drawings={drawings}
        onDrawingsChange={onDrawingsChange}
        activeTool={activeTool}
        onToolDone={onToolDone}
        drawColor={drawColor}
        selectedId={selectedDrawingId}
        onSelect={onSelectDrawing}
        onContextMenuAt={onJournalRequest}
        textPrompt={textPrompt}
        journalNotes={journalNotes}
        onJournalNoteClick={onJournalNoteClick}
      />
    </div>
  );
}
