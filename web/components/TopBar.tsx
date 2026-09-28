"use client";

import { useState } from "react";
import { ALL_TIMEFRAMES, type Timeframe } from "@/lib/types";

interface Props {
  ticker: string;
  timeframe: Timeframe;
  price: number | null;
  priceUp: boolean | null;
  isLive: boolean;
  statusText: string;
  showOrderPanel: boolean;
  onSymbolChange: (s: string) => void;
  onTimeframeChange: (tf: Timeframe) => void;
  onToggleOrderPanel: () => void;
}

export default function TopBar({
  ticker, timeframe, price, priceUp, isLive, statusText,
  showOrderPanel, onSymbolChange, onTimeframeChange, onToggleOrderPanel,
}: Props) {
  const [input, setInput] = useState(ticker);

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 6px", borderBottom: "1px solid var(--border)" }}>
      <span style={{ color: "var(--text-muted)" }}>Symbol:</span>
      <input
        value={input}
        onChange={(e) => setInput(e.target.value.toUpperCase())}
        onKeyDown={(e) => {
          if (e.key === "Enter" && input.trim()) onSymbolChange(input.trim());
        }}
        style={{ width: 90 }}
      />
      <select value={timeframe} onChange={(e) => onTimeframeChange(e.target.value as Timeframe)}>
        {ALL_TIMEFRAMES.map((tf) => (
          <option key={tf} value={tf}>{tf}</option>
        ))}
      </select>
      <span
        style={{
          fontSize: 18, fontWeight: "bold", minWidth: 90,
          color: priceUp == null ? "var(--text)" : priceUp ? "var(--up)" : "var(--down)",
        }}
      >
        {price != null ? price.toFixed(2) : "—"}
      </span>
      <div style={{ flex: 1 }} />
      <span style={{ color: isLive ? "var(--up)" : "var(--down)" }}>●</span>
      <span style={{ color: "var(--text-muted)" }} title={statusText}>{statusText}</span>
      <button
        onClick={onToggleOrderPanel}
        style={{ background: showOrderPanel ? "var(--accent)" : undefined }}
      >
        Trade Panel
      </button>
    </div>
  );
}
