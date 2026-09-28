"use client";

// Top-level app assembly: top bar, drawing toolbar, indicator sidebar,
// central chart, and the collapsible paper-trading panel. Port of
// ../main.py's MainWindow — wires the polled price feed to the chart's
// current candle and to the paper-trading engine.
import { useCallback, useEffect, useRef, useState } from "react";
import TopBar from "./TopBar";
import Sidebar from "./Sidebar";
import DrawingToolbar from "./DrawingToolbar";
import Chart, { type FillMarker, type OrderLine } from "./Chart";
import OrderPanel from "./OrderPanel";
import JournalDialog from "./JournalDialog";
import { config } from "@/lib/config";
import * as storage from "@/lib/storage";
import * as engine from "@/lib/paperEngine";
import { describeOrder } from "@/lib/orders";
import { atr as calcAtr } from "@/lib/indicators";
import { floorTimestamp } from "@/lib/time";
import { usePersistedPerKey } from "@/lib/hooks";
import {
  ALL_TIMEFRAMES, defaultIndicatorConfig, defaultOverlayConfig,
  type Candle, type DrawingKind, type JournalNote, type OrderSide, type OrderType, type ProfileMode, type Timeframe,
} from "@/lib/types";

type JournalDialogState =
  | { mode: "add"; ts: number; price: number | null }
  | { mode: "view"; note: JournalNote }
  | null;

export default function AppShell() {
  const initialSettings = storage.getSettings({ ticker: config.defaultTicker, timeframe: config.defaultTimeframe });
  const [ticker, setTicker] = useState(initialSettings.ticker);
  const [timeframe, setTimeframe] = useState<Timeframe>(
    ALL_TIMEFRAMES.includes(initialSettings.timeframe as Timeframe) ? (initialSettings.timeframe as Timeframe) : config.defaultTimeframe
  );

  const [candles, setCandles] = useState<Candle[]>([]);
  const [loadingMsg, setLoadingMsg] = useState<string>("Loading…");
  const [lastPrice, setLastPrice] = useState<number | null>(null);
  const [priceUp, setPriceUp] = useState<boolean | null>(null);
  const [isLive, setIsLive] = useState(false);
  const [statusText, setStatusText] = useState("connecting…");

  const [indicators, setIndicators] = useState(defaultIndicatorConfig());
  const [overlays, setOverlays] = useState(defaultOverlayConfig());
  const [profileMode, setProfileMode] = useState<ProfileMode>("off");
  const [marketProfileEnabled, setMarketProfileEnabled] = useState(false);

  const [activeTool, setActiveTool] = useState<DrawingKind | null>(null);
  const [selectedDrawingId, setSelectedDrawingId] = useState<string | null>(null);
  const [showOrderPanel, setShowOrderPanel] = useState(true);
  const [journalDialog, setJournalDialog] = useState<JournalDialogState>(null);

  const drawingKey = `${ticker}:${timeframe}`;
  const [drawings, setDrawings] = usePersistedPerKey(
    drawingKey,
    (k) => { const [t, tf] = k.split(":"); return storage.loadDrawings(t, tf); },
    (k, v) => { const [t, tf] = k.split(":"); storage.saveDrawings(t, tf, v); }
  );
  const [journalNotes, setJournalNotes] = usePersistedPerKey(ticker, storage.loadJournal, storage.saveJournal);

  const [paperState, setPaperState] = useState(() => storage.loadPaperState(engine.initialPaperState(config.startingBalance)));
  useEffect(() => storage.savePaperState(paperState), [paperState]);

  // Reset tool/selection when switching ticker+timeframe — a render-time
  // state adjustment (react.dev's "Adjusting state when a prop changes"
  // pattern) rather than an effect, since it must happen before paint.
  const [resetKey, setResetKey] = useState(drawingKey);
  if (resetKey !== drawingKey) {
    setResetKey(drawingKey);
    setSelectedDrawingId(null);
    setActiveTool(null);
  }

  useEffect(() => {
    storage.setSettings({ ticker, timeframe });
  }, [ticker, timeframe]);

  // ---- historical candles --------------------------------------------------
  useEffect(() => {
    let cancelled = false;
    // react.dev's own data-fetching pattern (set loading, then fetch); there's
    // no prior render this could be deferred to since it depends on [ticker, timeframe].
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoadingMsg(`Loading ${ticker} ${timeframe}…`);
    fetch(`/api/candles?symbol=${encodeURIComponent(ticker)}&timeframe=${timeframe}`)
      .then((r) => r.json())
      .then((json) => {
        if (cancelled) return;
        const c: Candle[] = json.candles ?? [];
        setCandles(c);
        setLoadingMsg(c.length ? "" : `No data for ${ticker} ${timeframe}`);
        if (c.length) {
          setLastPrice(c[c.length - 1].close);
        }
      })
      .catch(() => {
        if (!cancelled) setLoadingMsg(`Failed to load ${ticker} ${timeframe}`);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker, timeframe]);

  // ---- polling live price ---------------------------------------------------
  const lastPriceRef = useRef<number | null>(null);
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    let wait = Math.max(3, config.pollingIntervalSeconds);
    const base = wait;

    const tick = async () => {
      if (stopped) return;
      try {
        const res = await fetch(`/api/quote?symbol=${encodeURIComponent(ticker)}`);
        const json = await res.json();
        const price: number | null = json.price;
        if (price != null && !stopped) {
          setIsLive(true);
          setStatusText("polling (Yahoo Finance)");
          setPriceUp(lastPriceRef.current == null ? null : price >= lastPriceRef.current);
          lastPriceRef.current = price;
          setLastPrice(price);
          setCandles((prev) => appendOrUpdateCandle(prev, price, timeframe));
          setPaperState((prev) => engine.onPrice(prev, ticker, price));
          wait = base;
        } else {
          wait = Math.min(wait * 2, 30);
        }
      } catch {
        setIsLive(false);
        wait = Math.min(wait * 2, 30);
      }
      if (!stopped) timer = setTimeout(tick, wait * 1000);
    };

    timer = setTimeout(tick, 500);
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [ticker, timeframe]);

  // ---- journal --------------------------------------------------------------
  const handleJournalSave = useCallback(
    (text: string, tradeId: number | null) => {
      if (journalDialog?.mode !== "add") return;
      const note: JournalNote = {
        id: Date.now(), ticker, ts: journalDialog.ts, price: journalDialog.price,
        note: text, tradeId, createdAt: Date.now() / 1000,
      };
      setJournalNotes((prev) => [...prev, note]);
    },
    [journalDialog, ticker, setJournalNotes]
  );
  const handleJournalDelete = useCallback(
    (id: number) => setJournalNotes((prev) => prev.filter((n) => n.id !== id)),
    [setJournalNotes]
  );

  // ---- paper trading ----------------------------------------------------------
  const handleSubmitOrder = useCallback(
    (input: { side: OrderSide; type: OrderType; qty: number; limitPrice: number | null; stopPrice: number | null }) => {
      setPaperState((prev) => engine.submitOrder(prev, { ticker, ...input }));
    },
    [ticker]
  );

  const fillMarkers: FillMarker[] = paperState.orders
    .filter((o) => o.status === "filled" && o.ticker === ticker && o.filledAt != null && o.fillPrice != null)
    .map((o) => ({ time: o.filledAt!, price: o.fillPrice!, side: o.side, label: `${o.side.toUpperCase()} ${o.qty}` }));

  const orderLines: OrderLine[] = engine.openOrders(paperState, ticker)
    .filter((o) => o.limitPrice != null || o.stopPrice != null)
    .map((o) => ({
      key: String(o.id), price: (o.limitPrice ?? o.stopPrice)!, label: describeOrder(o),
      color: o.side === "buy" ? "#26a69a" : "#ef5350",
    }));

  const atrValue = indicators.atr.enabled && candles.length ? calcAtr(candles, 14).at(-1) ?? null : null;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <TopBar
        ticker={ticker}
        timeframe={timeframe}
        price={lastPrice}
        priceUp={priceUp}
        isLive={isLive}
        statusText={statusText}
        showOrderPanel={showOrderPanel}
        onSymbolChange={setTicker}
        onTimeframeChange={setTimeframe}
        onToggleOrderPanel={() => setShowOrderPanel((v) => !v)}
      />
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <DrawingToolbar
          activeTool={activeTool}
          onSelectTool={(k) => setActiveTool((cur) => (cur === k ? null : k))}
          onDeleteSelected={() => {
            if (!selectedDrawingId) return;
            setDrawings((prev) => prev.filter((d) => d.id !== selectedDrawingId));
            setSelectedDrawingId(null);
          }}
          onClearAll={() => setDrawings([])}
          hasSelection={selectedDrawingId != null}
        />
        <Sidebar
          indicators={indicators}
          onIndicatorsChange={setIndicators}
          overlays={overlays}
          onOverlaysChange={setOverlays}
          profileMode={profileMode}
          onProfileModeChange={setProfileMode}
          marketProfileEnabled={marketProfileEnabled}
          onMarketProfileChange={setMarketProfileEnabled}
          atrValue={atrValue}
        />
        <div style={{ flex: 1, position: "relative", minWidth: 0 }}>
          {candles.length === 0 && (
            <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)", zIndex: 1 }}>
              {loadingMsg}
            </div>
          )}
          <Chart
            candles={candles}
            indicators={indicators}
            overlays={overlays}
            profileMode={profileMode}
            marketProfileEnabled={marketProfileEnabled}
            drawings={drawings}
            onDrawingsChange={setDrawings}
            activeTool={activeTool}
            onToolDone={() => setActiveTool(null)}
            drawColor="#d1d4dc"
            selectedDrawingId={selectedDrawingId}
            onSelectDrawing={setSelectedDrawingId}
            fillMarkers={fillMarkers}
            journalNotes={journalNotes}
            onJournalRequest={(ts, price) => setJournalDialog({ mode: "add", ts, price })}
            onJournalNoteClick={(note) => setJournalDialog({ mode: "view", note })}
            orderLines={orderLines}
          />
        </div>
        {showOrderPanel && (
          <OrderPanel
            ticker={ticker}
            state={paperState}
            onSubmit={handleSubmitOrder}
            onCancel={(id) => setPaperState((prev) => engine.cancelOrder(prev, id))}
            onCancelAll={() => setPaperState((prev) => engine.cancelAllOrders(prev, ticker))}
            onReset={() => setPaperState(engine.initialPaperState(paperState.account.startingBalance))}
          />
        )}
      </div>

      {journalDialog?.mode === "add" && (
        <JournalDialog
          mode="add"
          ts={journalDialog.ts}
          price={journalDialog.price}
          trades={paperState.trades.filter((t) => t.ticker === ticker)}
          onSave={handleJournalSave}
          onClose={() => setJournalDialog(null)}
        />
      )}
      {journalDialog?.mode === "view" && (
        <JournalDialog
          mode="view"
          note={journalDialog.note}
          onDelete={() => handleJournalDelete(journalDialog.note.id)}
          onClose={() => setJournalDialog(null)}
        />
      )}
    </div>
  );
}

function appendOrUpdateCandle(candles: Candle[], price: number, timeframe: Timeframe): Candle[] {
  if (!candles.length) return candles;
  const bucket = floorTimestamp(Date.now() / 1000, timeframe);
  const last = candles[candles.length - 1];
  if (bucket > last.time) {
    return [...candles, { time: bucket, open: price, high: price, low: price, close: price, volume: 0 }];
  }
  const updated: Candle = { ...last, close: price, high: Math.max(last.high, price), low: Math.min(last.low, price) };
  return [...candles.slice(0, -1), updated];
}
