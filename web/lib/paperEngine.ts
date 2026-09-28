// Paper-trading engine: order matching, position tracking, P&L. Direct port
// of ../trading/paper.py's net-position model, reworked as pure functions
// over an immutable state object (instead of a Qt object with signals) so it
// plugs into a React reducer. Persistence lives in storage.ts.
import { checkFill } from "./orders";
import type { Account, Order, Position, Trade } from "./types";

export interface PaperState {
  account: Account;
  orders: Order[];
  trades: Trade[];
  positions: Record<string, Position>;
  lastPrice: Record<string, number>;
  nextOrderId: number;
  nextTradeId: number;
}

export function initialPaperState(startingBalance: number): PaperState {
  return {
    account: { startingBalance, cash: startingBalance, realizedPnl: 0 },
    orders: [],
    trades: [],
    positions: {},
    lastPrice: {},
    nextOrderId: 1,
    nextTradeId: 1,
  };
}

function clonePosition(p: Position): Position {
  return { ...p };
}

// Applies a signed fill to a position in place, returns close info if the
// fill closed/reduced/flipped the position (to realize P&L), else null.
function updatePosition(
  pos: Position,
  signed: number,
  price: number
): { closing: number; direction: 1 | -1; entry: number; realized: number } | null {
  const oldQty = pos.qty;
  if (oldQty === 0 || (oldQty > 0) === signed > 0) {
    const newQty = oldQty + signed;
    pos.avgPrice = newQty !== 0 ? (pos.avgPrice * Math.abs(oldQty) + price * Math.abs(signed)) / Math.abs(newQty) : 0;
    pos.qty = newQty;
    return null;
  }
  const closing = Math.min(Math.abs(signed), Math.abs(oldQty));
  const direction: 1 | -1 = oldQty > 0 ? 1 : -1;
  const entry = pos.avgPrice;
  const realized = (price - entry) * closing * direction;
  const remaining = Math.abs(signed) - closing;
  const newQty = oldQty + signed;
  pos.qty = newQty;
  if (remaining > 1e-9) pos.avgPrice = price;
  else if (Math.abs(newQty) < 1e-9) pos.avgPrice = 0;
  return { closing, direction, entry, realized };
}

export function submitOrder(
  state: PaperState,
  input: Pick<Order, "ticker" | "side" | "type" | "qty" | "limitPrice" | "stopPrice">
): PaperState {
  const order: Order = {
    id: state.nextOrderId,
    ...input,
    status: "open",
    createdAt: Date.now() / 1000,
    filledAt: null,
    fillPrice: null,
  };
  let next: PaperState = {
    ...state,
    nextOrderId: state.nextOrderId + 1,
    orders: [...state.orders, order],
  };
  const price = next.lastPrice[order.ticker];
  if (price != null) next = tryFill(next, order.id, price);
  return next;
}

export function cancelOrder(state: PaperState, orderId: number): PaperState {
  return {
    ...state,
    orders: state.orders.map((o) => (o.id === orderId && o.status === "open" ? { ...o, status: "cancelled" } : o)),
  };
}

export function cancelAllOrders(state: PaperState, ticker?: string): PaperState {
  return {
    ...state,
    orders: state.orders.map((o) =>
      o.status === "open" && (ticker == null || o.ticker === ticker) ? { ...o, status: "cancelled" } : o
    ),
  };
}

function tryFill(state: PaperState, orderId: number, price: number): PaperState {
  const order = state.orders.find((o) => o.id === orderId);
  if (!order) return state;
  const fillPrice = checkFill(order, price);
  if (fillPrice == null) return state;

  const filledOrder: Order = { ...order, status: "filled", fillPrice, filledAt: Date.now() / 1000 };
  const positions = { ...state.positions };
  const pos = clonePosition(positions[order.ticker] ?? { ticker: order.ticker, qty: 0, avgPrice: 0 });
  const signed = order.side === "buy" ? order.qty : -order.qty;
  const close = updatePosition(pos, signed, fillPrice);
  positions[order.ticker] = pos;

  let account = state.account;
  let trades = state.trades;
  let nextTradeId = state.nextTradeId;
  if (close) {
    account = { ...account, realizedPnl: account.realizedPnl + close.realized, cash: account.startingBalance + account.realizedPnl + close.realized };
    const trade: Trade = {
      id: nextTradeId,
      ticker: order.ticker,
      side: close.direction > 0 ? "long" : "short",
      qty: close.closing,
      entryPrice: close.entry,
      exitPrice: fillPrice,
      pnl: close.realized,
      entryTs: order.createdAt,
      exitTs: Date.now() / 1000,
    };
    trades = [...trades, trade];
    nextTradeId += 1;
  }

  return {
    ...state,
    orders: state.orders.map((o) => (o.id === orderId ? filledOrder : o)),
    positions,
    account,
    trades,
    nextTradeId,
  };
}

export function onPrice(state: PaperState, ticker: string, price: number): PaperState {
  let next: PaperState = { ...state, lastPrice: { ...state.lastPrice, [ticker]: price } };
  for (const o of next.orders) {
    if (o.status === "open" && o.ticker === ticker) {
      next = tryFill(next, o.id, price);
    }
  }
  return next;
}

export function unrealizedPnl(state: PaperState): number {
  let total = 0;
  for (const pos of Object.values(state.positions)) {
    if (Math.abs(pos.qty) < 1e-9) continue;
    const price = state.lastPrice[pos.ticker] ?? pos.avgPrice;
    total += (price - pos.avgPrice) * pos.qty;
  }
  return total;
}

export function equity(state: PaperState): number {
  return state.account.startingBalance + state.account.realizedPnl + unrealizedPnl(state);
}

export function positionPnl(state: PaperState, ticker: string): { pnl: number; pct: number } {
  const pos = state.positions[ticker];
  if (!pos || Math.abs(pos.qty) < 1e-9) return { pnl: 0, pct: 0 };
  const price = state.lastPrice[ticker] ?? pos.avgPrice;
  const pnl = (price - pos.avgPrice) * pos.qty;
  const pct = pos.avgPrice ? (price / pos.avgPrice - 1) * 100 * (pos.qty > 0 ? 1 : -1) : 0;
  return { pnl, pct };
}

export function openOrders(state: PaperState, ticker?: string): Order[] {
  return state.orders.filter((o) => o.status === "open" && (ticker == null || o.ticker === ticker));
}

export function stats(state: PaperState) {
  const wins = state.trades.filter((t) => t.pnl > 0);
  return {
    startingBalance: state.account.startingBalance,
    equity: equity(state),
    realizedPnl: state.account.realizedPnl,
    unrealizedPnl: unrealizedPnl(state),
    totalTrades: state.trades.length,
    winRate: state.trades.length ? (wins.length / state.trades.length) * 100 : 0,
  };
}
