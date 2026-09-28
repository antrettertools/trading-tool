export type Timeframe = "1m" | "5m" | "15m" | "30m" | "1h" | "4h" | "1d" | "1w";

export const ALL_TIMEFRAMES: Timeframe[] = [
  "1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w",
];

// epoch seconds (UTC) — matches lightweight-charts' UTCTimestamp
export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export type OrderSide = "buy" | "sell";
export type OrderType = "market" | "limit" | "stop" | "stop_limit";
export type OrderStatus = "open" | "filled" | "cancelled";

export interface Order {
  id: number;
  ticker: string;
  side: OrderSide;
  type: OrderType;
  qty: number;
  limitPrice: number | null;
  stopPrice: number | null;
  status: OrderStatus;
  createdAt: number;
  filledAt: number | null;
  fillPrice: number | null;
  stopTriggered?: boolean;
}

export interface Trade {
  id: number;
  ticker: string;
  side: "long" | "short";
  qty: number;
  entryPrice: number;
  exitPrice: number;
  pnl: number;
  entryTs: number;
  exitTs: number;
}

export interface Account {
  startingBalance: number;
  cash: number;
  realizedPnl: number;
}

export interface Position {
  ticker: string;
  qty: number;
  avgPrice: number;
}

export interface JournalNote {
  id: number;
  ticker: string;
  ts: number;
  price: number | null;
  note: string;
  tradeId: number | null;
  createdAt: number;
}

export type DrawingKind = "hline" | "vline" | "trend" | "rect" | "text";

export interface DrawingBase {
  id: string;
  kind: DrawingKind;
  color: string;
  width: number;
}

export interface HLineDrawing extends DrawingBase {
  kind: "hline";
  y: number;
}

export interface VLineDrawing extends DrawingBase {
  kind: "vline";
  x: number; // epoch seconds
}

export interface TrendDrawing extends DrawingBase {
  kind: "trend";
  p1: [number, number]; // [time, price]
  p2: [number, number];
}

export interface RectDrawing extends DrawingBase {
  kind: "rect";
  p1: [number, number];
  p2: [number, number];
}

export interface TextDrawing extends DrawingBase {
  kind: "text";
  x: number;
  y: number;
  text: string;
}

export type Drawing = HLineDrawing | VLineDrawing | TrendDrawing | RectDrawing | TextDrawing;

export interface MaConfig {
  id: string;
  kind: "EMA" | "SMA";
  period: number;
  color: string;
  width: number;
  enabled: boolean;
}

export interface IndicatorConfig {
  mas: MaConfig[];
  rsi: { enabled: boolean; period: number };
  macd: { enabled: boolean };
  bollinger: { enabled: boolean; period: number; mult: number };
  atr: { enabled: boolean };
  vwap: { enabled: boolean; bands: boolean };
  volumeMa: { enabled: boolean };
}

export interface OverlayConfig {
  prevDay: boolean;
  prevWeek: boolean;
  prevMonth: boolean;
  sessionOpen: boolean;
  overnight: boolean;
  nakedPoc: boolean;
  sessions: boolean;
}

export type ProfileMode = "off" | "visible" | "sessions";

export function defaultIndicatorConfig(): IndicatorConfig {
  return {
    mas: [],
    rsi: { enabled: false, period: 14 },
    macd: { enabled: false },
    bollinger: { enabled: false, period: 20, mult: 2.0 },
    atr: { enabled: false },
    vwap: { enabled: false, bands: true },
    volumeMa: { enabled: false },
  };
}

export function defaultOverlayConfig(): OverlayConfig {
  return {
    prevDay: false,
    prevWeek: false,
    prevMonth: false,
    sessionOpen: false,
    overnight: false,
    nakedPoc: false,
    sessions: false,
  };
}
