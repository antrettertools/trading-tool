"use client";

// Paper-trading side panel: account summary, order entry, open orders,
// positions, trade history. Port of ../ui/order_panel.py.
import { useState } from "react";
import type { OrderSide, OrderType } from "@/lib/types";
import { describeOrder } from "@/lib/orders";
import * as engine from "@/lib/paperEngine";
import type { PaperState } from "@/lib/paperEngine";

interface Props {
  ticker: string;
  state: PaperState;
  onSubmit: (input: { side: OrderSide; type: OrderType; qty: number; limitPrice: number | null; stopPrice: number | null }) => void;
  onCancel: (orderId: number) => void;
  onCancelAll: () => void;
  onReset: () => void;
}

const TYPE_LABELS: { label: string; value: OrderType }[] = [
  { label: "Market", value: "market" },
  { label: "Limit", value: "limit" },
  { label: "Stop", value: "stop" },
  { label: "Stop-Limit", value: "stop_limit" },
];

function pnlColor(v: number) {
  return v >= 0 ? "var(--up)" : "var(--down)";
}

export default function OrderPanel({ ticker, state, onSubmit, onCancel, onCancelAll, onReset }: Props) {
  const [side, setSide] = useState<OrderSide>("buy");
  const [type, setType] = useState<OrderType>("market");
  const [qty, setQty] = useState(10);
  const [limitPrice, setLimitPrice] = useState(0);
  const [stopPrice, setStopPrice] = useState(0);

  const s = engine.stats(state);
  const orders = engine.openOrders(state, ticker);
  const positions = Object.values(state.positions).filter((p) => Math.abs(p.qty) > 1e-9);
  const trades = state.trades.filter((t) => t.ticker === ticker).slice().reverse();

  const needsLimit = type === "limit" || type === "stop_limit";
  const needsStop = type === "stop" || type === "stop_limit";

  return (
    <div style={{ width: 300, padding: 8, borderLeft: "1px solid var(--border)", overflowY: "auto", display: "flex", flexDirection: "column", gap: 10 }}>
      <div className="group-box">
        <div className="group-title">Account</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4 }}>
          <span>Starting</span><b>${s.startingBalance.toLocaleString(undefined, { maximumFractionDigits: 2 })}</b>
          <span>Equity</span><b>${s.equity.toLocaleString(undefined, { maximumFractionDigits: 2 })}</b>
          <span>Realized P&L</span><b style={{ color: pnlColor(s.realizedPnl) }}>${s.realizedPnl.toFixed(2)}</b>
          <span>Unrealized</span><b style={{ color: pnlColor(s.unrealizedPnl) }}>${s.unrealizedPnl.toFixed(2)}</b>
          <span>Win rate</span><b>{s.winRate.toFixed(1)}%</b>
          <span>Trades</span><b>{s.totalTrades}</b>
        </div>
      </div>

      <div className="group-box">
        <div className="group-title">New Order</div>
        <div style={{ display: "flex", gap: 8, marginBottom: 6 }}>
          <label style={{ color: "var(--up)", fontWeight: "bold" }}>
            <input type="radio" checked={side === "buy"} onChange={() => setSide("buy")} /> BUY
          </label>
          <label style={{ color: "var(--down)", fontWeight: "bold" }}>
            <input type="radio" checked={side === "sell"} onChange={() => setSide("sell")} /> SELL
          </label>
        </div>
        <select value={type} onChange={(e) => setType(e.target.value as OrderType)} style={{ width: "100%", marginBottom: 6 }}>
          {TYPE_LABELS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
        </select>
        <input type="number" min={0.0001} value={qty} onChange={(e) => setQty(Number(e.target.value) || 0)} placeholder="Qty" style={{ width: "100%", marginBottom: 6 }} />
        {needsLimit && (
          <input type="number" min={0} step={0.01} value={limitPrice} onChange={(e) => setLimitPrice(Number(e.target.value) || 0)} placeholder="Limit" style={{ width: "100%", marginBottom: 6 }} />
        )}
        {needsStop && (
          <input type="number" min={0} step={0.01} value={stopPrice} onChange={(e) => setStopPrice(Number(e.target.value) || 0)} placeholder="Stop" style={{ width: "100%", marginBottom: 6 }} />
        )}
        <button
          style={{ width: "100%", marginBottom: 6 }}
          onClick={() => onSubmit({ side, type, qty, limitPrice: needsLimit ? limitPrice : null, stopPrice: needsStop ? stopPrice : null })}
        >
          Submit Order
        </button>
        <div style={{ display: "flex", gap: 6 }}>
          <button style={{ flex: 1 }} onClick={onCancelAll}>Cancel All</button>
          <button
            style={{ flex: 1 }}
            onClick={() => {
              if (window.confirm("Wipe all paper-trading history?")) onReset();
            }}
          >
            Reset
          </button>
        </div>
      </div>

      <div className="group-box">
        <div className="group-title">Open Orders</div>
        <table>
          <tbody>
            {orders.map((o) => (
              <tr key={o.id}>
                <td>{describeOrder(o)}</td>
                <td>{o.status}</td>
                <td><button onClick={() => onCancel(o.id)} style={{ padding: "1px 5px" }}>✕</button></td>
              </tr>
            ))}
            {orders.length === 0 && <tr><td style={{ color: "var(--text-muted)" }}>No open orders</td></tr>}
          </tbody>
        </table>
      </div>

      <div className="group-box">
        <div className="group-title">Positions</div>
        <table>
          <thead><tr><th>Sym</th><th>Qty</th><th>Avg</th><th>P&L</th></tr></thead>
          <tbody>
            {positions.map((p) => {
              const { pnl, pct } = engine.positionPnl(state, p.ticker);
              return (
                <tr key={p.ticker}>
                  <td>{p.ticker}</td>
                  <td>{p.qty}</td>
                  <td>{p.avgPrice.toFixed(2)}</td>
                  <td style={{ color: pnlColor(pnl) }}>${pnl.toFixed(2)} ({pct >= 0 ? "+" : ""}{pct.toFixed(2)}%)</td>
                </tr>
              );
            })}
            {positions.length === 0 && <tr><td style={{ color: "var(--text-muted)" }}>Flat</td></tr>}
          </tbody>
        </table>
      </div>

      <div className="group-box">
        <div className="group-title">Trade History</div>
        <table>
          <thead><tr><th>Side</th><th>Entry</th><th>Exit</th><th>P&L</th><th>Qty</th></tr></thead>
          <tbody>
            {trades.map((t) => (
              <tr key={t.id}>
                <td>{t.side}</td>
                <td>{t.entryPrice.toFixed(2)}</td>
                <td>{t.exitPrice.toFixed(2)}</td>
                <td style={{ color: pnlColor(t.pnl) }}>${t.pnl.toFixed(2)}</td>
                <td>{t.qty}</td>
              </tr>
            ))}
            {trades.length === 0 && <tr><td style={{ color: "var(--text-muted)" }}>No trades yet</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
